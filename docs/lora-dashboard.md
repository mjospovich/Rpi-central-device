# LoRa dashboard (LorBee edge control UI)

## Overview

Single-page web dashboard for monitoring devices on ChirpStack MQTT: **LorBee** edge units (custom **fPort 10** commands) and **Decentlab DL-IAM** sensors (factory downlink format). Live uplink feed, split command panel, and ACK tracking for LorBee edges.

## Port

| Port | Protocol | Purpose |
|------|----------|---------|
| 3000 | HTTP | Dashboard web UI |

## Architecture

```
Mosquitto (1883)                    ChirpStack REST API (8090)
    │                                        │
    │ application/+/device/+/event/up        │ POST /api/devices/{devEui}/queue
    ▼                                        ▲
┌──────────────────────────────────────────────┐
│           lora-dashboard (Flask)             │
│                                              │
│  MQTT subscriber → SSE push → Browser        │
│  /api/command → payload builder → CS REST     │
└──────────────────────────────────────────────┘
         │
         ▼
   Browser (port 3000)
```

## Files

| Path | Purpose |
|------|---------|
| `lora-dashboard/app.py` | Flask app — MQTT listener, SSE endpoint, command proxy, device tracking |
| `lora-dashboard/decentlab_downlink.py` | Decentlab-style downlink hex + CRC-16 + base64 (DL-IAM subset) |
| `lora-dashboard/templates/index.html` | Single-page dark UI with live feed, command panel, history |
| `lora-dashboard/requirements.txt` | Python dependencies (Flask, paho-mqtt, requests, gunicorn) |
| `lora-dashboard/Dockerfile` | Container build |

Runtime **per-device overrides** are stored in the **`lora_dashboard_data`** volume at `/data/device_downlink_overrides.json` inside the container.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHIRPSTACK_API_URL` | `http://localhost:8090` | ChirpStack REST API base URL |
| `CHIRPSTACK_API_TOKEN` | *(required)* | ChirpStack API key for enqueuing downlinks |
| `MQTT_BROKER` | `localhost` | Mosquitto broker host |
| `MQTT_PORT` | `1883` | Mosquitto broker port |
| `DASHBOARD_PORT` | `3000` | Web UI port |
| `EDGE_DEVEUIS` | *(empty)* | Optional allow-list: if set, **only** these DevEUIs get LorBee commands; everyone else is command-hidden unless Decentlab rules match |
| `DL_IAM_DEVEUIS` | *(empty)* | Optional explicit DevEUIs for **factory** Decentlab downlinks (overrides name rules for odd names) |
| `DECENTLAB_DEVICE_NAME_SUBSTRINGS` | *(empty)* | Comma-separated substrings (case-insensitive) matched against ChirpStack **device name**; any match → Decentlab command set |
| `DEVICE_DOWNLINK_OVERRIDES_FILE` | `/data/device_downlink_overrides.json` | JSON map `devEui → lorbee \| decentlab \| none`; updated from the **Command set** dropdown in the UI |
| `DL_IAM_FPORT` | `1` | Application fPort for Decentlab downlinks (must match device profile) |
| `EXCLUDED_DEVEUIS` | *(empty)* | Comma-separated devEUIs with **no** downlink UI under automatic rules |
| `UPLINK_CACHE_MAX` | `500` | Max uplinks kept in RAM; served on reload via `GET /api/uplinks` |
| `INTERVAL_GAP_SAMPLES` | `20` | Inter-uplink gaps used for average interval / next-uplink estimate |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard page |
| `GET` | `/events` | SSE stream (uplinks, command updates, MQTT status, `uplink_cache_cleared`) |
| `GET` | `/api/devices` | Command-eligible devices + `downlinkFamily` (`lorbee` \| `decentlab`) + timing fields |
| `POST` | `/api/device-downlink-preference` | Body `{ "devEui", "family": "auto" \| "lorbee" \| "decentlab" \| "none" }` |
| `GET` | `/api/device-stats` | All devices seen on MQTT with timing estimates |
| `GET` | `/api/uplinks` | Cached uplinks (`?limit=`) newest first |
| `DELETE` | `/api/uplinks` | Clear uplink cache and interval stats |
| `GET` | `/api/decentlab/commands` | Decentlab opcodes exposed in the UI |
| `POST` | `/api/command` | LorBee: `{devEui, command, params}` · DL-IAM: `{devEui, opcode, param}` |
| `GET` | `/api/command/history` | Recent command history with ACK status |
| `GET` | `/api/queue/<devEui>` | Proxy: ChirpStack downlink queue |
| `DELETE` | `/api/queue/<devEui>` | Proxy: flush downlink queue for the device |

## DevEUI handling

- All DevEUIs are **normalized** to lowercase hex without separators (`:` / `-` / spaces).
- Same **device name**, different DevEUIs → separate chips with shortened EUI in the UI.

## Why not auto-detect LorBee vs DL-IAM from payload?

MQTT `object` fields are ambiguous. The dashboard uses **device name** substrings, optional DevEUI lists, and UI **Command set** overrides so the wrong downlink family is never sent.

## Uplink feed, filters, and timing

- Ring buffer + `GET /api/uplinks` for refresh.
- Filters: device, search, ACK-only.
- **Next uplink** is a heuristic from average inter-arrival gaps (Class A is not exact).

## Downlink queue

ChirpStack REST supports list + flush entire queue only (no per-item delete). The dashboard surfaces **Flush queue** accordingly.

## Downlink commands — two families

### LorBee edge (custom)

| Command | Payload | Parameters |
|---------|---------|------------|
| `ping` | `[0x01]` | None |
| `set_interval` | `[0x02, hi, lo]` | `seconds` (30–3600) |
| `permit_join` | `[0x03, duration]` | `seconds` (0–254) |

Enqueued on **fPort 10**, base64 via ChirpStack REST.

### DL-IAM / Decentlab (factory)

Uses the [Decentlab downlink command encoder](https://decentlab.github.io/decentlab-decoders/downlink-command-encoder.html) framing (opcode + param + CRC-16 → base64). The UI exposes a **subset** of commands (sampling/send period, DR, with optional +save).

## ACK tracking

LorBee edges can emit `_ack` in the decoded `object` after a command. The dashboard matches pending rows to **ACK OK** / **ACK FAIL**. This requires your **payload codec** to pass `_ack` through on the uplink after the downlink.

## FAQ — different JSON shapes

The parser accepts **`object`** when present, else scalar / small dict fields at the **root** (flat MQTT JSON).

## Setup

1. ChirpStack UI → **API keys** → create a token with permissions to enqueue downlinks.
2. Set `CHIRPSTACK_API_TOKEN` in `.env` (see `.env.example`).
3. `docker compose up -d lora-dashboard`
4. Open **`http://<host>:3000`**

## See also

- [ChirpStack](chirpstack.md)
- [Related projects](related-projects.md) — **LorBeePlugin**
