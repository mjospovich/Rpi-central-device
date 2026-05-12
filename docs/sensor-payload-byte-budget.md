# Sensor payload byte budget (LoRa-oriented)

**Purpose:** Byte-budget reference for **LoRaWAN application payloads**: compact binary layouts vs. fat MQTT/JSON. This repo’s runtime path is **ChirpStack → MQTT → Influx** (JSON on the broker); the **over-the-air** payload for devices like the DL-IAM remains binary.

**Sections 1–3** are *hypothetical* mappings (“if you sent similar quantities as LoRa binary”) useful when designing custom codecs. **Section 4** documents the **Decentlab DL-IAM** wire format used with `chirpstack-decoders/DL-IAM.js`.

| # | Focus | Notes |
|---|--------|--------|
| 1 | Temperature / humidity | Example binary packing for env sensors |
| 2 | Motion / presence | Example binary packing for PIR-style fields |
| 3 | Air quality (PM) | Example binary packing for PM + particle size |
| 4 | DL-IAM (Decentlab) | Actual codec and on-wire layout in this repo |

---

## 1. Temperature / humidity (Zigbee)

**Fields observed in production state** (`temperature`, `humidity`, `battery`, `linkquality`). Node-RED forwards on change for `temperature`, `humidity`, `battery` (see `nodered` flows).

| Field | Meaning | Desired type (LoRa) | Bytes | Range / notes |
|-------|---------|---------------------|-------|----------------|
| `temperature` | °C | **int16** BE, scale **0.01°C** (e.g. 2243 → 22.43°C) | **2** | −327.68…+327.67°C; enough for climate |
| `humidity` | % RH | **uint16** BE, scale **0.01%** OR **uint8** if 1% steps | **2** or **1** | uint8: 0–100%; uint16: finer |
| `battery` | % | **uint8** | **1** | 0–100 |
| `linkquality` | LQI | **uint8** (optional) | **0–1** | 0–255; omit on LoRa if not applicable |

**Recommended binary record (no LQI):**

- **4 bytes** — `int16` temp (0.01°C) + `uint8` humidity (0–100%) + `uint8` battery  
- **5 bytes** — `int16` temp + `uint16` humidity (0.01% steps) + `uint8` battery  

**Optional:** prepend **1-byte sensor/message ID** for multi-sensor gateways → **+1 byte**.

---

## 2. Motion / presence (Zigbee)

**Fields in production state** include `occupancy`, `battery`, `linkquality`, `voltage` (mV), plus metadata (`illumination` string, `motion_timeout`, OTA `update`). Telegraf consumes **occupancy** and **battery** (`docs/telegraf.md`).

| Field | Meaning | Desired type (LoRa) | Bytes | Notes |
|-------|---------|---------------------|-------|-------|
| `occupancy` | PIR state | **uint8** (0/1) or 1 bit in flags | **1** | bool |
| `battery` | % | **uint8** | **1** | 0–100 |
| `linkquality` | LQI | **uint8** (optional) | **0–1** | |
| `voltage` | Battery mV | **uint16** BE (optional) | **0–2** | e.g. 2800 mV; skip if only % is enough |

**Recommended minimal binary record:** **2 bytes** (`occupancy` + `battery`).  
**With LQI:** **3 bytes**.  
**With voltage:** **4 bytes** (occ + batt + uint16 mV).

---

## 3. SPS30 (PM + particle size)

**Exact MQTT JSON** from `sps30-collector/app/main.py`:

| Field | Meaning | Desired type (LoRa) | Bytes | Notes |
|-------|---------|---------------------|-------|-------|
| `pm1_0` | µg/m³ | **float32** BE **or** uint16 (scale 0.1 µg/m³) | **4** or **2** | float32: simplest; uint16 max ~6553.5 µg/m³ at 0.1 step |
| `pm2_5` | µg/m³ | same | **4** or **2** | |
| `pm4_0` | µg/m³ | same | **4** or **2** | |
| `pm10` | µg/m³ | same | **4** or **2** | |
| `typical_particle_size_um` | µm | **float32** **or** uint16 (e.g. µm × 1000) | **4** or **2** | |

**Full precision (all float32):** **20 bytes**.  
**Compact (five uint16 with agreed scale):** **10 bytes** (verify range vs. your max PM).

---

## 4. DL-IAM (Decentlab — already LoRaWAN binary)

Decoder: `chirpstack-decoders/DL-IAM.js`. On the wire, values are **big-endian uint16** (`read_int`), after a fixed header.

### 4.1 Header (always)

| Part | Bytes | Type | Notes |
|------|-------|------|-------|
| Protocol version | 1 | uint8 | must be `2` |
| Device ID | 2 | uint16 BE | Decentlab device id |
| Flags | 2 | uint16 BE | bit *i* = sensor block *i* present |

**Header subtotal: 5 bytes.**

### 4.2 Payload blocks (each uint16 = **2 bytes** on wire)

Only blocks with the corresponding flag bit set are present, in order:

| Block order | Included if flag bit | Raw uint16 words | On-wire bytes | Decoded metrics (decoder output names) |
|-------------|----------------------|------------------|---------------|------------------------------------------|
| 0 | bit 0 | 1 word | 2 | `battery_voltage` (V = raw/1000) |
| 1 | bit 1 | 2 words | 4 | `air_temperature` (°C), `air_humidity` (%) |
| 2 | bit 2 | 1 word | 2 | `barometric_pressure` (Pa × 0.5 in convert → ×2 in decoder) |
| 3 | bit 3 | 2 words | 4 | `ambient_light_visible_infrared`, `ambient_light_infrared`, derived `illuminance` (lx) |
| 4 | bit 4 | 3 words | 6 | `co2_concentration` (ppm), `co2_sensor_status`, `raw_ir_reading` |
| 5 | bit 5 | 1 word | 2 | `activity_counter` |
| 6 | bit 6 | 1 word | 2 | `total_voc` (ppb) |

**Maximum application payload** (all seven blocks enabled):  
5 + 2 + 4 + 2 + 4 + 6 + 2 + 2 = **27 bytes**.

**Minimum** depends on device configuration (which flags the sensor sets); only present blocks are transmitted.

Decoded value types are **floats/ints in JSON** after decoding (e.g. temperature, humidity, CO₂ ppm); the **radio payload** is the uint16 stream above, not JSON.

---

## Summary: per-sensor binary totals (LoRa-oriented)

| Sensor | Minimal useful binary size | “Full” / typical binary size |
|--------|----------------------------|------------------------------|
| Temp / humidity | **4 B** (int16 + uint8 RH + uint8 batt) | **5 B** with uint16 RH; +1 B optional ID |
| Motion | 2–3 B | 4 B with mV |
| SPS30 | 10 B (5× uint16, scaled) | 20 B (5× float32) |
| DL-IAM | **variable** (flags) | **27 B** max (all blocks) |

**If you concatenated one compact frame for temp + motion + SPS30** (single custom uplink, not Decentlab): order-dependent, roughly **4 + 3 + 20 = 27 B** (4 B temp/humid + 3 B motion + 5×float32 SPS30) or **4 + 3 + 10 = 17 B** (compact uint16 SPS30), **before** any frame header, MIC, or device addressing (those are LoRaWAN layers, not application payload).

---

## Reference: MQTT/JSON (not LoRa-efficient)

Rough order of magnitude for **serialized JSON** strings used today (length varies with whitespace and numeric digits):

| Stream | Typical JSON size |
|--------|-------------------|
| Temp/humid (few numeric keys) | ~60–100 B |
| Motion (full Z2M object) | ~150–400+ B if many keys |
| SPS30 (five floats) | ~120–180 B |
| ChirpStack uplink **wrapper** (includes `object`, base64 `data`, metadata) | **kB scale** over MQTT; the **application payload** inside remains the binary size in §4 |

For LoRa planning, use the **binary** figures above; JSON is useful for broker debugging, not airtime.

---

## LoRaWAN limits (context only)

Application payload length depends on **region, DR/SF, and FOpts**; EU868 often allows on the order of **tens of bytes** per uplink at low data rates. The DL-IAM **27-byte** full frame is already within a typical LoRaWAN application payload budget; always confirm against your configured data rate and regional spec.

---

## Related docs

- [ChirpStack](chirpstack.md) — DL-IAM decoder path  
- [Telegraf](telegraf.md) — MQTT → Influx for `nodered/lorawan/#`  
- [LoRa Pipeline Explained](lora-pipeline-explained.md) — end-to-end DL-IAM flow  
- [Related projects](related-projects.md) — **Rpi-edge-alert** / **LorBeePlugin** payload and codec pointers  
