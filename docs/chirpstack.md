# ChirpStack

**Service:** `chirpstack`, `chirpstack-gateway-bridge`, `chirpstack-rest-api`  
**Images:** `chirpstack/chirpstack:4`, `chirpstack/chirpstack-gateway-bridge:4`, `chirpstack/chirpstack-rest-api:4`  
**Ports:** 8081 (Web UI), 8090 (REST API), 1700/udp (gateway)

## Overview

ChirpStack is the LoRaWAN network server. It receives uplinks from LoRaWAN gateways via the Gateway Bridge, manages devices and applications, and publishes decoded payloads to MQTT. **It uses the same Mosquitto broker** as Node-RED and Telegraf (`host.docker.internal:1883`).

## How It Works

1. **Gateway Bridge** — Listens on UDP 1700 for Semtech packet-forwarder traffic. Converts to JSON and publishes to MQTT topics `eu868/gateway/<id>/event/*`.
2. **ChirpStack** — Subscribes to gateway events, handles join requests, routes uplinks to applications, runs payload decoders, publishes to `application/<id>/device/<dev_eui>/event/up`.
3. **REST API** — gRPC-to-REST proxy for the web UI and external integrations.

## Files Covered

| Path | Purpose |
|------|---------|
| `chirpstack/` | Main config, region definitions (EU868, etc.) |
| `chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml` | Gateway bridge config (MQTT, UDP 1700) |
| `chirpstack-postgresql/initdb/` | PostgreSQL extensions |
| `chirpstack-decoders/DL-IAM.js` | Decentlab DL-IAM payload decoder |

## Local Network Routes

| URL | Port | Purpose |
|-----|------|---------|
| `http://<host>:8081` | 8081 | ChirpStack Web UI — applications, devices, gateways |
| `http://<host>:8090` | 8090 | REST API (for integrations) |

## MQTT Topics (ChirpStack → Mosquitto)

| Topic pattern | Publisher | Subscribers |
|----------------|-----------|-------------|
| `eu868/gateway/<id>/event/*` | Gateway Bridge | ChirpStack (internal) |
| `application/<app_id>/device/<dev_eui>/event/up` | ChirpStack | Node-RED (this stack) |

## Setup Steps (Without Gateway)

### 1. Start ChirpStack

```bash
cd /path/to/Rpi-central-device
docker compose up -d mosquitto chirpstack-postgres chirpstack-redis chirpstack chirpstack-gateway-bridge chirpstack-rest-api
```

Mosquitto must be up; ChirpStack connects to `host.docker.internal:1883`.

### 2. First Login

1. Open `http://<host>:8081` (or `http://localhost:8081`)
2. Default login: **admin** / **admin** — you will be prompted to change the password
3. **Security:** Change the API secret in `chirpstack/chirpstack.toml` (`[api] secret=`) before production. Generate with: `openssl rand -base64 32`

### 3. Create Application

1. **Tenants** → Create tenant (e.g. "Lab")
2. **Applications** → Create application (e.g. "Sensors")
3. **Integrations** → Ensure MQTT integration is enabled (default)

### 4. Create Device Profile for DL-IAM

1. **Device profiles** → Create profile
2. Name: `DL-IAM`
3. **Payload codec** → Custom JavaScript
4. Paste the contents of `chirpstack-decoders/DL-IAM.js`

### 5. Add DL-IAM Device

1. **Devices** → Add device
2. **DevEUI** — from the sensor label or packaging (8 bytes, e.g. `0123456789abcdef`)
3. **Device profile** — select `DL-IAM`
4. **Activation** — OTAA (recommended) or ABP
5. **OTAA:** Set AppEUI and AppKey (from sensor docs or generate)
6. **ABP:** Set DevAddr, NwkSKey, AppSKey

### 6. When Gateway Arrives

See **[Gateway Setup: Laird Sentrius RG1xx](gateway-setup-laird-rg1xx.md)** for a step-by-step guide.

Summary:
1. **Gateways** → Add gateway (Gateway ID = gateway EUI from label)
2. Configure the gateway: **Semtech Forwarder**, Server = `<your-pi-ip>`, Port = `1700`
3. Power the DL-IAM — it will join (OTAA) and start sending uplinks

## DL-IAM Sensor (Decentlab)

The DL-IAM (Indoor Ambiance Monitor) measures:

| Measurement | Unit | Notes |
|-------------|------|-------|
| CO2 concentration | ppm | |
| Total VOC | ppb | |
| Air temperature | °C | |
| Air humidity | % | |
| Barometric pressure | Pa | |
| Illuminance | lx | |
| Activity counter | — | Motion/presence |
| Battery voltage | V | |

Payload decoder: `chirpstack-decoders/DL-IAM.js` (from [Decentlab decoders](https://github.com/decentlab/decentlab-decoders)).

## Node-RED → Telegraf → InfluxDB Cloud

Decoded uplinks are consumed by **Node-RED**: `application/+/device/+/event/up` → flatten `object` → `nodered/lorawan/<measurement>` → **Telegraf** → **InfluxDB Cloud** (`INFLUX_BUCKET`). For **`zigbee_network_*`**-style measurement names, Node-RED also publishes **`nodered/lorawan_edge`** with `measurement=lora_rpi_edge`. See **[Node-RED](nodered.md)** and **[Telegraf](telegraf.md)**.

### Uplink JSON shape (decoded)

```json
{
  "deduplicationId": "...",
  "deviceInfo": { "devEui": "...", ... },
  "data": "base64...",
  "object": { "air_temperature": 22.5, "co2_concentration": 450, ... }
}
```

The `object` field contains the decoded payload when a codec is configured on the device profile.

## Dependencies

- **Mosquitto** — Must be running (ChirpStack uses it via `host.docker.internal`)
- **PostgreSQL, Redis** — ChirpStack internal (`chirpstack-postgres`, `chirpstack-redis`)

## See also

- [Related projects](related-projects.md) — edge devices (**LorBeePlugin**, **Rpi-edge-alert**) that join this ChirpStack  
- [LoRa pipeline explained](lora-pipeline-explained.md)  
- [Gateway setup (Laird RG1xx)](gateway-setup-laird-rg1xx.md)

## Port Summary

| Port | Service |
|------|---------|
| 8081 | ChirpStack Web UI |
| 8090 | ChirpStack REST API |
| 1700/udp | Gateway Bridge — Semtech packet-forwarder (EU868) |

## Notes

- ChirpStack uses `host.docker.internal` to reach the host's Mosquitto. Requires Docker 20.10+ with `extra_hosts: host.docker.internal:host-gateway`.
- Gateway Bridge listens on UDP 1700. Ensure the firewall allows it if the gateway is on another machine.
- For Basic Station gateways (TCP 3001), use `chirpstack-gateway-bridge-basicstation-eu868.toml` instead.
