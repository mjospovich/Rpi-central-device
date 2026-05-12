# References and upstream software

This stack is **integration and configuration** on top of published open-source projects and services. Below are the main upstreams so credit and docs stay traceable (this is not an exhaustive dependency tree of every transitive library).

## LoRaWAN network server

| Project | Role here | Links |
|---------|-----------|--------|
| **ChirpStack** | Network server, gateway bridge, REST API (`chirpstack/chirpstack:4`, `chirpstack-gateway-bridge:4`, `chirpstack-rest-api:4`) | [Website](https://www.chirpstack.io/), [Documentation](https://www.chirpstack.io/docs/), [GitHub — chirpstack](https://github.com/chirpstack/chirpstack) |

ChirpStack configuration and region snippets under `chirpstack/` and `chirpstack-gateway-bridge/` follow project conventions; see ChirpStack’s own licensing in their repositories.

## MQTT, automation, metrics

| Project | Role here | Links |
|---------|-----------|--------|
| **Eclipse Mosquitto** | MQTT broker (`eclipse-mosquitto:latest`) | [Project](https://mosquitto.org/), [GitHub](https://github.com/eclipse/mosquitto) |
| **Node-RED** | Flow runtime (`nodered/node-red:latest`) | [Project](https://nodered.org/), [GitHub](https://github.com/node-red/node-red) |
| **Telegraf** | Metrics agent, MQTT consumer → InfluxDB v2 output (`telegraf:1.29`) | [InfluxData — Telegraf](https://www.influxdata.com/time-series-platform/telegraf/), [GitHub](https://github.com/influxdata/telegraf) |
| **InfluxDB Cloud** | Hosted time-series backend (configured via `INFLUX_*` in `.env`) | [InfluxData](https://www.influxdata.com/), [Cloud](https://www.influxdata.com/products/influxdb-cloud/) |

## Databases (ChirpStack dependencies)

| Project | Role here | Links |
|---------|-----------|--------|
| **PostgreSQL** | ChirpStack application storage (`postgres:14-alpine`) | [PostgreSQL](https://www.postgresql.org/) |
| **Redis** | ChirpStack metadata cache (`redis:7-alpine`) | [Redis](https://redis.io/), [GitHub](https://github.com/redis/redis) |

## LoRa dashboard (`lora-dashboard`)

Built with **Python** and common libraries; see `lora-dashboard/requirements.txt` for pinned packages. Notable upstreams:

| Project | Links |
|---------|--------|
| **Flask** | [Pallets](https://flask.palletsprojects.com/), [GitHub](https://github.com/pallets/flask) |
| **Paho MQTT** (Python) | [Eclipse Paho](https://www.eclipse.org/paho/), [paho.mqtt.python](https://github.com/eclipse/paho.mqtt.python) |
| **Requests** | [GitHub](https://github.com/psf/requests) |

Decentlab-oriented decoding/downlink patterns are documented by **Decentlab** (payload formats, encoder tool); see [Decentlab decoders](https://github.com/decentlab/decentlab-decoders) and their [downlink command encoder](https://decentlab.github.io/decentlab-decoders/downlink-command-encoder.html).

## Device payload codec (example)

| Asset | Links |
|-------|--------|
| **DL-IAM** example codec (`chirpstack-decoders/DL-IAM.js`) | Derived from [Decentlab decoders](https://github.com/decentlab/decentlab-decoders) — use ChirpStack’s JavaScript codec integration as described in [ChirpStack docs](https://www.chirpstack.io/docs/). |

## Optional visualization

| Project | Links |
|---------|--------|
| **Grafana** | [Grafana Labs](https://grafana.com/), [GitHub](https://github.com/grafana/grafana) |

---

If you add or swap container images, extend this file so the **image name → upstream project** mapping stays obvious for readers and for license compliance.
