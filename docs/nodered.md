# Node-RED

**Service:** `nodered`  
**Image:** `nodered/node-red:latest`  
**Network:** `host` — editor on **1880**

## Overview

Node-RED subscribes to ChirpStack **application** uplinks on MQTT, normalizes the decoded `object` into flat JSON, and publishes to topics consumed by **Telegraf**.

## Flow (committed)

**Tab:** `LoRaWAN → Influx`

1. **MQTT in** — `application/+/device/+/event/up` (JSON from ChirpStack).
2. **Function** — `Normalize ChirpStack object`:
   - Reads `deviceInfo` and decoded `object`.
   - Derives an Influx **measurement** name from device/profile naming (e.g. DL-IAM → `dl_iam_<n>`, generic → `lorawan_misc`; optional `zigbee_network_*` for devices named `lora-radio-*`).
   - Flattens numeric and string fields, adds `dev_eui`, `time_gmt2`, and alarm helper fields when `alarm_fields` is present in the payload.
   - Emits one MQTT message per nested sensor block if the codec returns multiple objects.
3. **MQTT out** — dynamic topic from each message, usually `nodered/lorawan/<measurement>`.
4. For measurements whose name starts with `zigbee_network_`, a duplicate message is also sent to **`nodered/lorawan_edge`** with `measurement` forced to **`lora_rpi_edge`** (and `original_measurement` set) for optional Telegraf routing.

## Files

| Path | Purpose |
|------|---------|
| `nodered/data/flows.json` | Flow definitions |
| `nodered/data/settings.js` | Node-RED settings (`flowFile`, etc.) |

Do not commit `nodered/data/flows_cred.json` if you add MQTT credentials; it is gitignored.

## Tailoring for your devices

Edit the **Normalize ChirpStack object** function if your ChirpStack **device names** or **measurement** naming rules differ. Telegraf expects JSON with `measurement` plus `time_gmt2` (RFC3339 with offset).

## Dependencies

- **Mosquitto** on `localhost:1883`.

## See also

- [Related projects](related-projects.md) — edge stacks (**LorBeePlugin**, **Rpi-edge-alert**) whose LoRa devices join this ChirpStack  
- [ChirpStack](chirpstack.md) — uplink topic and codecs  
- [Telegraf](telegraf.md) — MQTT inputs and Influx output  
- [LoRa pipeline explained](lora-pipeline-explained.md)
