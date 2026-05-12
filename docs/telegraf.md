# Telegraf

**Service:** `telegraf`  
**Image:** `telegraf:1.29`  
**Network:** `host`

## Overview

Telegraf subscribes to Node-RED output topics on Mosquitto, parses JSON, and writes to **InfluxDB Cloud** using `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, and `INFLUX_BUCKET` from `.env`. There is no InfluxDB container in this project.

## Inputs

| MQTT topic(s) | Purpose |
|---------------|---------|
| `nodered/lorawan/#` | Primary LoRaWAN metrics (dynamic measurement from JSON `measurement` key) |
| `nodered/lorawan_edge` | Optional duplicate stream (`lora_rpi_edge` measurement) |

JSON parsing uses `json_name_key = "measurement"`, `json_time_key = "time_gmt2"`, and tag keys `dev_eui`, `device_name`, `sensor_name`, `sensor_type`.

## Output

Single **`outputs.influxdb_v2`** block:

- `urls = ["${INFLUX_URL}"]`
- `token`, `organization`, `bucket` from environment

## Files

| Path | Purpose |
|------|---------|
| `telegraf/telegraf.conf` | Inputs and output |
| `.env` | `INFLUX_*` variables (`env_file` in Compose) |

## Troubleshooting

1. `docker logs telegraf 2>&1 | grep -iE 'error|401|404'` — token, org, bucket, or URL issues.
2. `mosquitto_sub -h localhost -t 'nodered/lorawan/#' -v` — confirm JSON when devices send uplinks.
3. Ensure `INFLUX_ORG` matches what Influx shows for the token (name or ID).

## Dependencies

- **Mosquitto**, **Node-RED** (for transformed topics), outbound HTTPS to **InfluxDB Cloud** at `INFLUX_URL`.
