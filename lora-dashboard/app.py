"""LorBee Edge Control Dashboard — Flask + SSE + MQTT backend."""

import json
import os
import queue
import threading
import time
from base64 import b64decode, b64encode
from collections import deque
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
import requests
from flask import Flask, Response, jsonify, render_template, request

from decentlab_downlink import DECENTLAB_UI_COMMANDS, build_decentlab_hex, decentlab_hex_to_b64

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CHIRPSTACK_API_URL = os.getenv("CHIRPSTACK_API_URL", "http://localhost:8090")
CHIRPSTACK_API_TOKEN = os.getenv("CHIRPSTACK_API_TOKEN", "")
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "3000"))
UPLINK_CACHE_MAX = int(os.getenv("UPLINK_CACHE_MAX", "500"))
INTERVAL_GAP_SAMPLES = int(os.getenv("INTERVAL_GAP_SAMPLES", "20"))

UPLINK_TOPIC = "application/+/device/+/event/up"

# Devices that accept our custom downlink protocol (fPort 10).
# Comma-separated devEUIs in env, or empty to auto-discover from uplinks.
_edge_devs = os.getenv("EDGE_DEVEUIS", "")


def normalize_deveui(raw: str | None) -> str:
    """Canonical DevEUI for dict keys and API calls (lowercase hex, no separators)."""
    if not raw:
        return ""
    s = str(raw).strip().lower().replace("-", "").replace(":", "").replace(" ", "")
    return s


EDGE_DEVEUIS: set[str] = {
    normalize_deveui(d) for d in _edge_devs.split(",") if normalize_deveui(d)
}

# DevEUIs to exclude from *any* downlink UI (unknown / read-only devices).
_excluded = os.getenv("EXCLUDED_DEVEUIS", "")
EXCLUDED_DEVEUIS: set[str] = {
    normalize_deveui(d) for d in _excluded.split(",") if normalize_deveui(d)
}

# Decentlab DL-IAM (and similar): use factory downlink format, not LorBee fPort 10.
_dl_iam = os.getenv("DL_IAM_DEVEUIS", "")
DL_IAM_DEVEUIS: set[str] = {
    normalize_deveui(d) for d in _dl_iam.split(",") if normalize_deveui(d)
}

DL_IAM_FPORT = int(os.getenv("DL_IAM_FPORT", "1"))

# Comma-separated substrings (case-insensitive) matched against ChirpStack device name
# to classify as Decentlab / DL-IAM without listing every DevEUI.
_decentlab_name_subs = os.getenv("DECENTLAB_DEVICE_NAME_SUBSTRINGS", "")
DECENTLAB_DEVICE_NAME_SUBSTRINGS: tuple[str, ...] = tuple(
    s.strip().lower() for s in _decentlab_name_subs.split(",") if s.strip()
)

# Per-device command-set overrides (survives restarts). JSON object devEUI -> lorbee|decentlab|none.
OVERRIDES_FILE = os.getenv(
    "DEVICE_DOWNLINK_OVERRIDES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_downlink_overrides.json"),
)

overrides_lock = threading.Lock()
device_downlink_overrides: dict[str, str] = {}


def _load_downlink_overrides() -> None:
    path = OVERRIDES_FILE
    merged: dict[str, str] = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    nk = normalize_deveui(str(k))
                    if not nk or not isinstance(v, str):
                        continue
                    vv = v.strip().lower()
                    if vv in ("lorbee", "decentlab", "none"):
                        merged[nk] = vv
        except (OSError, json.JSONDecodeError) as exc:
            app.logger.warning("Could not load %s: %s", path, exc)
    with overrides_lock:
        device_downlink_overrides.clear()
        device_downlink_overrides.update(merged)


def _save_downlink_overrides_locked() -> None:
    """Persist overrides; caller must hold overrides_lock."""
    path = OVERRIDES_FILE
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, mode=0o755, exist_ok=True)
        except OSError as exc:
            app.logger.error("Could not create overrides directory %s: %s", parent, exc)
            return
    tmp = path + ".tmp"
    blob = json.dumps(dict(sorted(device_downlink_overrides.items())), indent=2)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(blob)
        os.replace(tmp, path)
    except OSError as exc:
        app.logger.error("Could not save downlink overrides: %s", exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _name_matches_decentlab(device_name: str) -> bool:
    if not DECENTLAB_DEVICE_NAME_SUBSTRINGS:
        return False
    nl = (device_name or "").lower()
    return any(sub in nl for sub in DECENTLAB_DEVICE_NAME_SUBSTRINGS)


def _automatic_downlink_family(dev_eui: str, device_name: str) -> str:
    """Classification when no per-device override is set."""
    e = normalize_deveui(dev_eui)
    if e in EXCLUDED_DEVEUIS:
        return "none"
    if e in DL_IAM_DEVEUIS:
        return "decentlab"
    if _name_matches_decentlab(device_name):
        return "decentlab"
    if EDGE_DEVEUIS and e not in EDGE_DEVEUIS:
        return "none"
    return "lorbee"


def device_downlink_preference(dev_eui: str) -> str:
    """UI / API: auto = follow env + name rules; otherwise forced family."""
    e = normalize_deveui(dev_eui)
    with overrides_lock:
        p = device_downlink_overrides.get(e)
    if p in ("lorbee", "decentlab", "none"):
        return p
    return "auto"


def device_downlink_family(dev_eui: str) -> str:
    """Effective family for /api/command: lorbee, decentlab, or none."""
    e = normalize_deveui(dev_eui)
    with overrides_lock:
        o = device_downlink_overrides.get(e)
        if o in ("lorbee", "decentlab", "none"):
            return o
    name = str(devices_seen.get(e, {}).get("name") or "")
    return _automatic_downlink_family(e, name)


# ---------------------------------------------------------------------------
# Shared state (in-memory, no DB)
# ---------------------------------------------------------------------------
sse_subscribers: list[queue.Queue] = []
sse_lock = threading.Lock()

devices_seen: dict[str, dict] = {}  # devEui -> {name, lastSeen}

_load_downlink_overrides()
command_history: list[dict] = []  # [{id, devEui, deviceName, command, params, time, status}]
cmd_counter = 0
cmd_lock = threading.Lock()

uplink_seq = 0
uplink_cache: deque[dict[str, Any]] = deque(maxlen=UPLINK_CACHE_MAX)
uplink_cache_lock = threading.Lock()

# Per-device uplink timing: gaps between consecutive uplink timestamps (server time from payload).
device_interval_stats: dict[str, dict[str, Any]] = {}
interval_stats_lock = threading.Lock()

COMMAND_NAMES = {1: "Ping", 2: "Set Uplink Interval", 3: "Permit Zigbee Join"}


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------
def build_ping() -> str:
    return b64encode(bytes([0x01])).decode()


def build_set_interval(seconds: int) -> str:
    seconds = max(30, min(3600, seconds))
    return b64encode(bytes([0x02, (seconds >> 8) & 0xFF, seconds & 0xFF])).decode()


def build_permit_join(duration: int) -> str:
    duration = max(0, min(254, duration))
    return b64encode(bytes([0x03, duration])).decode()


PAYLOAD_BUILDERS = {
    "ping": lambda _: build_ping(),
    "set_interval": lambda p: build_set_interval(int(p.get("seconds", 60))),
    "permit_join": lambda p: build_permit_join(int(p.get("seconds", 120))),
}

COMMAND_IDS = {"ping": 1, "set_interval": 2, "permit_join": 3}


def _normalize_ack_dict(raw: dict | None) -> dict | None:
    """Codec may use cmd_id or cmdId; align for _process_ack."""
    if not raw or not isinstance(raw, dict):
        return None
    cid = raw.get("cmd_id")
    if cid is None:
        cid = raw.get("cmdId")
    try:
        cid_i = int(cid) if cid is not None else None
    except (TypeError, ValueError):
        cid_i = None
    if cid_i is None:
        return None
    suc = raw.get("success")
    if suc is None:
        suc = raw.get("Success", False)
    return {"cmd_id": cid_i, "success": bool(suc)}


def _split_object_ack_and_sensors(obj: Any) -> tuple[dict | None, dict]:
    """Strip _ack (or ack) from ChirpStack decoded object; return (ack, sensors)."""
    if not isinstance(obj, dict):
        return None, {}
    rest = dict(obj)
    raw_ack = rest.pop("_ack", None)
    if raw_ack is None:
        raw_ack = rest.pop("ack", None)
    ack = _normalize_ack_dict(raw_ack) if isinstance(raw_ack, dict) else None
    return ack, rest


def _parse_object_field(raw: Any) -> dict | None:
    """`object` may be a dict or a JSON string (some bridges)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            o = json.loads(raw)
            return o if isinstance(o, dict) else None
        except json.JSONDecodeError:
            return None
    return None


# Root keys to ignore when treating the uplink JSON as "flat" codec output (ChirpStack + RF meta).
_UPLINK_ROOT_SKIP_LOWER = frozenset(
    {
        "deduplicationid",
        "time",
        "deviceinfo",
        "rxinfo",
        "txinfo",
        "confirmed",
        "fport",
        "fcnt",
        "adr",
        "dr",
        "devaddr",
        "data",
        "object",
        "applicationid",
        "applicationname",
        "tenantid",
        "tenantname",
        "deviceprofileid",
        "deviceprofilename",
        "devicename",
        "deveui",
        "deviceclassenabled",
        "tags",
        "gatewayid",
        "uplinkid",
        "nstime",
        "regioncommonid",
        "region_config_id",
        "regionconfigid",
        "channel",
        "latitude",
        "longitude",
        "context",
        "crcstatus",
        "frequency",
        "bandwidth",
        "spreadingfactor",
        "coderate",
        "codingrate",
        "rssi",
        "snr",
        "lorasnr",
        "gwtime",
        "publishedat",
    }
)


def _flat_sensors_from_root(payload: dict) -> dict[str, Any]:
    """Use decoded fields that appear at JSON root (same codec, alternate layout / tooling)."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if not isinstance(k, str):
            continue
        lk = k.lower()
        if lk in _UPLINK_ROOT_SKIP_LOWER:
            continue
        if lk.startswith("_"):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict) and (
            "sensor_type" in v or "sensorType" in v or "entry_id" in v or "entryId" in v
        ):
            out[k] = v
        # skip lists (e.g. mis-placed rxInfo) and other nested blobs
        if len(out) >= 48:
            break
    return out


def _sensors_and_ack_from_payload(payload: dict) -> tuple[dict | None, dict[str, Any]]:
    """Prefer nested `object`; if empty, use scalar / small-dict fields at JSON root."""
    ack: dict | None = None
    sensors: dict[str, Any] = {}

    parsed_obj = _parse_object_field(payload.get("object"))
    if parsed_obj:
        a, sens = _split_object_ack_and_sensors(parsed_obj)
        ack = a
        if sens:
            sensors = sens

    if not sensors:
        flat = _flat_sensors_from_root(payload)
        if flat:
            sensors = flat

    if ack is None:
        raw_ack = payload.get("_ack")
        if isinstance(raw_ack, dict):
            ack = _normalize_ack_dict(raw_ack)

    return ack, sensors


def _merge_deveui_aliases(canonical: str) -> None:
    """If the same device was keyed under another casing/format, merge into canonical."""
    if not canonical:
        return

    for k in list(devices_seen.keys()):
        if k != canonical and normalize_deveui(k) == canonical:
            old = devices_seen.pop(k, None)
            if not old:
                continue
            cur = devices_seen.setdefault(canonical, {"name": "", "lastSeen": 0.0})
            cur["lastSeen"] = max(cur["lastSeen"], old["lastSeen"])
            if len(old.get("name") or "") > len(cur.get("name") or ""):
                cur["name"] = old["name"]

    with interval_stats_lock:
        for k in list(device_interval_stats.keys()):
            if k != canonical and normalize_deveui(k) == canonical:
                old_st = device_interval_stats.pop(k, None)
                if not old_st:
                    continue
                can_st = device_interval_stats.setdefault(
                    canonical, {"gaps": deque(maxlen=INTERVAL_GAP_SAMPLES), "last_ts": None}
                )
                for g in list(old_st.get("gaps") or []):
                    can_st["gaps"].append(g)
                a, b = can_st.get("last_ts"), old_st.get("last_ts")
                if a is not None and b is not None:
                    can_st["last_ts"] = max(a, b)
                elif b is not None:
                    can_st["last_ts"] = b

    with overrides_lock:
        merged_ov = False
        for k in list(device_downlink_overrides.keys()):
            if k != canonical and normalize_deveui(k) == canonical:
                v = device_downlink_overrides.pop(k, None)
                if v:
                    device_downlink_overrides.setdefault(canonical, v)
                    merged_ov = True
        if merged_ov:
            _save_downlink_overrides_locked()


def _parse_iso_to_epoch(s: str) -> float:
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return time.time()


def _epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _update_device_interval_stats(dev_eui: str, uplink_epoch: float) -> None:
    with interval_stats_lock:
        st = device_interval_stats.setdefault(
            dev_eui, {"gaps": deque(maxlen=INTERVAL_GAP_SAMPLES), "last_ts": None}
        )
        last = st["last_ts"]
        if last is not None:
            gap = uplink_epoch - last
            if gap >= 1.0:
                st["gaps"].append(gap)
        st["last_ts"] = uplink_epoch


def _device_timing(dev_eui: str) -> dict[str, Any]:
    with interval_stats_lock:
        st = device_interval_stats.get(dev_eui)
        if not st:
            return {
                "avgIntervalSec": None,
                "nextUplinkEst": None,
                "intervalSamples": 0,
                "lastUplinkAt": None,
            }
        gaps = deque(st["gaps"])
        last_ts = st["last_ts"]
    last_iso = _epoch_to_iso(last_ts) if last_ts else None
    if not gaps:
        return {
            "avgIntervalSec": None,
            "nextUplinkEst": None,
            "intervalSamples": 0,
            "lastUplinkAt": last_iso,
        }
    avg = sum(gaps) / len(gaps)
    next_est = (last_ts + avg) if last_ts else None
    return {
        "avgIntervalSec": round(avg, 1),
        "nextUplinkEst": _epoch_to_iso(next_est) if next_est else None,
        "intervalSamples": len(gaps),
        "lastUplinkAt": last_iso,
    }


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------
def broadcast_sse(event: str, data: dict):
    payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    dead: list[queue.Queue] = []
    with sse_lock:
        for q in sse_subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_subscribers.remove(q)


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties):
    app.logger.info("MQTT connected (rc=%s), subscribing to uplinks", reason_code)
    client.subscribe(UPLINK_TOPIC)
    broadcast_sse("mqtt_status", {"connected": True})


def on_disconnect(client, userdata, flags, reason_code, properties):
    app.logger.warning("MQTT disconnected (rc=%s)", reason_code)
    broadcast_sse("mqtt_status", {"connected": False})


def on_message(client, userdata, msg):
    global uplink_seq
    try:
        payload = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    dev_info = payload.get("deviceInfo") or {}
    raw_eui = dev_info.get("devEui") or dev_info.get("dev_eui") or ""
    dev_eui = normalize_deveui(raw_eui)
    if not dev_eui:
        return

    _merge_deveui_aliases(dev_eui)

    dev_name = dev_info.get("deviceName") or dev_info.get("device_name") or dev_eui
    ack, sensors = _sensors_and_ack_from_payload(payload)
    rx = (payload.get("rxInfo") or [{}])[0]
    ts = payload.get("time", datetime.now(timezone.utc).isoformat())

    devices_seen[dev_eui] = {
        "name": dev_name,
        "lastSeen": time.time(),
    }

    uplink_epoch = _parse_iso_to_epoch(ts)
    _update_device_interval_stats(dev_eui, uplink_epoch)

    dl_fam = device_downlink_family(dev_eui)
    dl_pref = device_downlink_preference(dev_eui)

    raw_b64 = payload.get("data")
    raw_len: int | None = None
    if isinstance(raw_b64, str) and raw_b64:
        try:
            raw_len = len(b64decode(raw_b64))
        except Exception:
            raw_len = None

    uplink_data = {
        "time": ts,
        "devEui": dev_eui,
        "deviceName": dev_name,
        "sensors": sensors,
        "rssi": rx.get("rssi"),
        "snr": rx.get("snr"),
        "ack": ack,
        "fPort": payload.get("fPort"),
        "rawPayloadLen": raw_len,
        "downlinkFamily": dl_fam,
        "downlinkPreference": dl_pref,
    }
    with uplink_cache_lock:
        uplink_seq += 1
        cache_entry = {"seq": uplink_seq, **uplink_data}
        uplink_cache.append(cache_entry)
    broadcast_sse("uplink", cache_entry)

    if ack:
        _process_ack(dev_eui, ack)


def _process_ack(dev_eui: str, ack: dict):
    cmd_id = ack.get("cmd_id")
    if cmd_id is None:
        return
    success = bool(ack.get("success", False))
    with cmd_lock:
        for cmd in reversed(command_history):
            if cmd["status"] != "Queued":
                continue
            if normalize_deveui(cmd["devEui"]) != dev_eui:
                continue
            try:
                if int(cmd["cmdId"]) != int(cmd_id):
                    continue
            except (TypeError, ValueError):
                continue
            cmd["status"] = "ACK OK" if success else "ACK FAIL"
            broadcast_sse("cmd_update", cmd)
            break


def _mark_queued_flushed(dev_eui: str) -> None:
    with cmd_lock:
        for cmd in command_history:
            if normalize_deveui(cmd["devEui"]) == dev_eui and cmd["status"] == "Queued":
                cmd["status"] = "Flushed"
                broadcast_sse("cmd_update", cmd)


# ---------------------------------------------------------------------------
# MQTT client (background thread)
# ---------------------------------------------------------------------------
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message


def start_mqtt():
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            mqtt_client.loop_forever()
        except Exception as exc:
            app.logger.error("MQTT connection failed: %s — retrying in 5s", exc)
            time.sleep(5)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/events")
def events():
    q: queue.Queue = queue.Queue(maxsize=256)
    with sse_lock:
        sse_subscribers.append(q)

    def stream():
        try:
            while True:
                try:
                    payload = q.get(timeout=30)
                    yield payload
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with sse_lock:
                if q in sse_subscribers:
                    sse_subscribers.remove(q)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/devices")
def api_devices():
    """Devices that can receive downlinks: LorBee (fPort 10) or DL-IAM (Decentlab)."""
    now = time.time()
    result = []
    for dev_eui, info in devices_seen.items():
        fam = device_downlink_family(dev_eui)
        if fam == "none":
            continue
        timing = _device_timing(dev_eui)
        result.append({
            "devEui": dev_eui,
            "name": info["name"],
            "online": (now - info["lastSeen"]) < 600,
            "downlinkFamily": fam,
            "downlinkPreference": device_downlink_preference(dev_eui),
            **timing,
        })
    return jsonify(result)


@app.route("/api/device-downlink-preference", methods=["POST"])
def api_device_downlink_preference():
    """Set per-device command set: auto (rules), lorbee, decentlab, or none (hide commands)."""
    body = request.json or {}
    dev_eui = normalize_deveui(body.get("devEui", ""))
    fam = (body.get("family") or "").strip().lower()
    if not dev_eui:
        return jsonify({"error": "Invalid devEui"}), 400
    if fam not in ("auto", "lorbee", "decentlab", "none"):
        return jsonify({"error": "family must be auto, lorbee, decentlab, or none"}), 400
    with overrides_lock:
        if fam == "auto":
            device_downlink_overrides.pop(dev_eui, None)
        else:
            device_downlink_overrides[dev_eui] = fam
        _save_downlink_overrides_locked()
    eff = device_downlink_family(dev_eui)
    pref = device_downlink_preference(dev_eui)
    return jsonify({
        "ok": True,
        "devEui": dev_eui,
        "downlinkFamily": eff,
        "downlinkPreference": pref,
    })


@app.route("/api/decentlab/commands")
def api_decentlab_commands():
    """Decentlab opcodes exposed in the UI (subset of official encoder)."""
    return jsonify(list(DECENTLAB_UI_COMMANDS))


@app.route("/api/device-stats")
def api_device_stats():
    """All devices seen on MQTT with uplink interval estimates (for dashboard chips)."""
    now = time.time()
    out = []
    for dev_eui, info in devices_seen.items():
        out.append({
            "devEui": dev_eui,
            "name": info["name"],
            "online": (now - info["lastSeen"]) < 600,
            **_device_timing(dev_eui),
        })
    out.sort(key=lambda x: (x["name"] or x["devEui"]).lower())
    return jsonify(out)


@app.route("/api/uplinks")
def api_uplinks():
    """Recent uplinks from server cache (newest first)."""
    limit = min(int(request.args.get("limit", 200)), UPLINK_CACHE_MAX)
    with uplink_cache_lock:
        items = list(uplink_cache)[-limit:]
    items.reverse()
    for row in items:
        de = normalize_deveui(row.get("devEui", "") or "")
        if de:
            row["devEui"] = de
            if "downlinkFamily" not in row:
                row["downlinkFamily"] = device_downlink_family(de)
            if "downlinkPreference" not in row:
                row["downlinkPreference"] = device_downlink_preference(de)
    return jsonify({"items": items, "maxCached": UPLINK_CACHE_MAX})


@app.route("/api/uplinks", methods=["DELETE"])
def api_uplinks_clear():
    """Clear uplink cache and reset per-device interval stats (avg / next est)."""
    with uplink_cache_lock:
        uplink_cache.clear()
    with interval_stats_lock:
        device_interval_stats.clear()
    broadcast_sse("uplink_cache_cleared", {})
    return jsonify({"ok": True})


@app.route("/api/command", methods=["POST"])
def api_command():
    global cmd_counter
    body = request.json or {}
    dev_eui = normalize_deveui(body.get("devEui", ""))
    if not dev_eui:
        return jsonify({"error": "Invalid devEui"}), 400

    family = device_downlink_family(dev_eui)
    if family == "none":
        return jsonify({"error": "Device not eligible for downlink"}), 400

    headers = {
        "Content-Type": "application/json",
        "Grpc-Metadata-Authorization": f"Bearer {CHIRPSTACK_API_TOKEN}",
    }

    if family == "lorbee":
        command = body.get("command", "").strip()
        params = body.get("params") or {}
        if command not in PAYLOAD_BUILDERS:
            return jsonify({"error": "Invalid command"}), 400
        b64_payload = PAYLOAD_BUILDERS[command](params)
        f_port = 10
        hist_cmd = command
        hist_cmd_id = COMMAND_IDS[command]
        hist_params = params
        hist_label = None
        status = "Queued"
    else:
        opcode = str(body.get("opcode", "")).strip().upper().zfill(4)[-4:]
        try:
            param = int(body.get("param", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid param"}), 400
        meta = next((c for c in DECENTLAB_UI_COMMANDS if str(c["opcode"]) == opcode), None)
        if not meta:
            return jsonify({"error": "Unknown Decentlab opcode"}), 400
        lo, hi = int(meta["param_min"]), int(meta["param_max"])
        if param < lo or param > hi:
            return jsonify({"error": f"param must be {lo}…{hi}"}), 400
        try:
            hex_cmd = build_decentlab_hex(opcode, param)
            b64_payload = decentlab_hex_to_b64(hex_cmd)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        f_port = DL_IAM_FPORT
        hist_cmd = f"dl:{opcode}"
        hist_cmd_id = 0
        hist_params = {"opcode": opcode, "param": param, "hex": hex_cmd}
        hist_label = str(meta["name"])
        status = "Sent"

    cs_body = {
        "queueItem": {
            "devEui": dev_eui,
            "confirmed": False,
            "fPort": f_port,
            "data": b64_payload,
        }
    }

    try:
        resp = requests.post(
            f"{CHIRPSTACK_API_URL}/api/devices/{dev_eui}/queue",
            json=cs_body, headers=headers, timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"ChirpStack API error: {exc}"}), 502

    with cmd_lock:
        cmd_counter += 1
        entry: dict[str, Any] = {
            "id": cmd_counter,
            "devEui": dev_eui,
            "deviceName": devices_seen.get(dev_eui, {}).get("name", dev_eui),
            "family": family,
            "command": hist_cmd,
            "cmdId": hist_cmd_id,
            "params": hist_params,
            "time": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }
        if hist_label:
            entry["cmdDisplay"] = hist_label
        command_history.append(entry)
        if len(command_history) > 200:
            command_history.pop(0)

    broadcast_sse("cmd_update", entry)
    return jsonify(entry), 201


@app.route("/api/command/history")
def api_command_history():
    return jsonify(list(reversed(command_history[-50:])))


@app.route("/api/queue/<dev_eui>")
def api_queue(dev_eui: str):
    """Proxy to ChirpStack GET queue for a device."""
    dev_eui = normalize_deveui(dev_eui)
    if not dev_eui:
        return jsonify({"error": "Invalid devEui"}), 400
    headers = {"Grpc-Metadata-Authorization": f"Bearer {CHIRPSTACK_API_TOKEN}"}
    try:
        resp = requests.get(
            f"{CHIRPSTACK_API_URL}/api/devices/{dev_eui}/queue",
            headers=headers, timeout=10,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except requests.RequestException as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/queue/<dev_eui>", methods=["DELETE"])
def api_flush_queue(dev_eui: str):
    """Flush entire downlink queue for a device (ChirpStack has no per-item delete in REST)."""
    dev_eui = normalize_deveui(dev_eui)
    if not dev_eui:
        return jsonify({"error": "Invalid devEui"}), 400
    headers = {"Grpc-Metadata-Authorization": f"Bearer {CHIRPSTACK_API_TOKEN}"}
    try:
        resp = requests.delete(
            f"{CHIRPSTACK_API_URL}/api/devices/{dev_eui}/queue",
            headers=headers, timeout=10,
        )
        resp.raise_for_status()
        _mark_queued_flushed(dev_eui)
        return jsonify({"ok": True})
    except requests.RequestException as exc:
        return jsonify({"error": str(exc)}), 502


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=start_mqtt, daemon=True).start()
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, threaded=True)
