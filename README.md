# Rpi-central-device

LoRaWAN **network server** and **metrics pipeline** on a Raspberry Pi (or Linux host): **ChirpStack**, **Mosquitto**, **Node-RED**, **Telegraf** → **InfluxDB Cloud**, and an optional **LoRa dashboard** (live uplinks + downlinks). Decoded uplinks are also normalized for time series and can feed **Grafana** on top of Cloud.


This repo is the **central** side of a split design: field / edge stacks (Zigbee + LoRa device, or air-quality + LoRa uplinks) live in companion repositories and **join through your gateway** to ChirpStack here.

---

## Related edge repositories

These projects are built to work **with** this central device—they communicate over LoRa to your gateway, which forwards to **ChirpStack** on this machine:

| Repository | Description |
|------------|-------------|
| [**LorBeePlugin**](https://github.com/mjospovich/LorBeePlugin) | Pi stack with **Zigbee2MQTT**, MQTT, Node-RED merges, and a **LoRaWAN end-device** for ChirpStack. |
| [**Rpi-edge-alert**](https://github.com/mjospovich/Rpi-edge-alert) | Edge **SPS30 + BME680**, Node-RED, optional calibration, **LoRaWAN v5** uplinks (ChirpStack-friendly). |

How they fit together: **[`docs/related-projects.md`](docs/related-projects.md)**.

---

## What runs here

| Service | Role | Default port |
|---------|------|--------------|
| Mosquitto | MQTT broker (ChirpStack, Node-RED, Telegraf) | 1883 |
| ChirpStack | LoRaWAN network server + web UI | 8081 |
| ChirpStack REST API | HTTP API (integrations, automation) | 8090 |
| Gateway bridge | Semtech UDP → MQTT | 1700/udp |
| PostgreSQL / Redis | ChirpStack backing stores | (internal) |
| Node-RED | `application/.../event/up` → Telegraf-friendly JSON | 1880 |
| Telegraf | MQTT → **InfluxDB Cloud** (`influxdb_v2`) | — |
| LoRa dashboard | Live MQTT feed + LorBee / DL-IAM downlinks via ChirpStack REST | 3000 |

There is **no** InfluxDB container; the edge host only needs outbound HTTPS to your Cloud region.

---

## Quick start

1. Clone the repo and create **`.env`** from **`.env.example`** (InfluxDB Cloud + **`CHIRPSTACK_API_TOKEN`** if you use the LoRa dashboard).
2. Start the stack:  
   `docker compose up -d`
3. Open ChirpStack: `http://<host>:8081` (default `admin` / `admin` — change password and API secret for production).
4. Register gateways and devices (see companion repos for OTAA keys and codecs).
5. Node-RED: `http://<host>:1880` — use the **LoRaWAN → Influx** flow after edits.
6. LoRa dashboard: `http://<host>:3000` — details ([`docs/lora-dashboard.md`](docs/lora-dashboard.md)).

---

## Data path

```text
LoRaWAN device → gateway → UDP :1700 → gateway-bridge → MQTT
  → ChirpStack → application/+/device/+/event/up
  → Node-RED → nodered/lorawan/# (optional nodered/lorawan_edge)
  → Telegraf → InfluxDB Cloud
```

---

## Documentation

Full index, reading order, and diagrams: **[`docs/README.md`](docs/README.md)**

| Doc | Topic |
|-----|--------|
| [docs/README.md](docs/README.md) | Hub — start here for navigation |
| [docs/lora-pipeline-explained.md](docs/lora-pipeline-explained.md) | End-to-end uplink path (beginner-friendly) |
| [docs/related-projects.md](docs/related-projects.md) | **LorBeePlugin**, **Rpi-edge-alert**, central vs edge |
| [docs/chirpstack.md](docs/chirpstack.md) | ChirpStack services, MQTT, setup |
| [docs/lora-dashboard.md](docs/lora-dashboard.md) | Live uplinks + downlink UI (port 3000) |
| [docs/mosquitto.md](docs/mosquitto.md) | Broker |
| [docs/nodered.md](docs/nodered.md) | Flows and topic contract |
| [docs/telegraf.md](docs/telegraf.md) | MQTT → Cloud |
| [docs/influxdb.md](docs/influxdb.md) | Cloud env vars |
| [docs/grafana.md](docs/grafana.md) | Optional dashboards |
| [docs/gateway-setup-laird-rg1xx.md](docs/gateway-setup-laird-rg1xx.md) | Example Laird gateway |
| [docs/sensor-payload-byte-budget.md](docs/sensor-payload-byte-budget.md) | Optional LoRa payload byte planning |

---

## Make targets

| Target | Action |
|--------|--------|
| `make up` | `docker compose up -d` |
| `make down` | `docker compose down` |
| `make logs` | Tail Telegraf, Node-RED, Mosquitto, LoRa dashboard |

---

## Region note

Default gateway bridge topics use **EU868** (`chirpstack-gateway-bridge/chirpstack-gateway-bridge.toml`). Other regions: use the matching templates under `chirpstack-gateway-bridge/` and align `chirpstack/` region configs.

---

## Security

- `mosquitto.conf` allows anonymous MQTT for lab LANs; lock down for production.
- Rotate ChirpStack **API secret** (`chirpstack/chirpstack.toml`) before exposing 8081/8090 beyond the LAN.
- **`CHIRPSTACK_API_TOKEN`** (LoRa dashboard) is a separate ChirpStack API key — minimal scope, keep it out of git.
- Never commit **`.env`** or **`nodered/data/flows_cred.json`**.

---

## License

See [LICENSE](LICENSE).
