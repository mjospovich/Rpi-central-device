# InfluxDB Cloud

**Storage for this stack:** **InfluxDB Cloud** only. **Telegraf** is the sole writer: it uses the `influxdb_v2` output with values from `.env`. There is **no** `influxdb` service in `docker-compose.yml`.

## What you configure

| Variable | Description |
|----------|-------------|
| `INFLUX_URL` | Cloud API base URL (HTTPS), e.g. `https://<region>.aws.cloud2.influxdata.com` |
| `INFLUX_TOKEN` | API token with **write** permission to the bucket |
| `INFLUX_ORG` | Organization — use the ID or name shown in Cloud for your token |
| `INFLUX_BUCKET` | Bucket name where LoRaWAN measurements should land |

Create the org, bucket, and token in the **InfluxDB Cloud** UI (or CLI). Use the same region URL your account shows.

## Verifying writes

1. **Cloud UI** → **Data Explorer** → query by measurement (from your codecs / Node-RED naming, e.g. `dl_iam_1`) and tags such as `dev_eui`.
2. **Telegraf**: `docker logs telegraf 2>&1 | tail -40` — look for HTTP errors (401/404 often mean wrong org, bucket, or token).

## Related docs

- [Telegraf](telegraf.md) — MQTT inputs and `influxdb_v2` output
- [Grafana](grafana.md) — dashboards against Cloud

## Dependencies

The Pi only needs **outbound HTTPS** to `INFLUX_URL` so Telegraf can write. No InfluxDB process runs on the edge host.
