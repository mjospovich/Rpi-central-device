# Grafana (optional)

This repository does **not** ship a Grafana container. Most users run Grafana on another machine, Grafana Cloud, or the same Pi as a separate install.

## Connect Grafana to InfluxDB Cloud (same as Telegraf)

1. In Grafana: **Connections → Add new connection → InfluxDB**.
2. **Query language:** Flux.
3. **URL:** Your **InfluxDB Cloud** region URL — the same host as `INFLUX_URL` in `.env` (HTTPS).
4. **Organization:** `INFLUX_ORG` from `.env`.
5. **Token:** Prefer a **read-only** Cloud API token for dashboards; Telegraf keeps using a write-capable token in `.env`.

## Tips

- Match **bucket** to `INFLUX_BUCKET`.
- Example Flux: `from(bucket: "your-bucket") |> range(start: v.timeRangeStart) |> filter(fn: (r) => r["_measurement"] =~ /dl_iam/)`

## Security

Use TLS (Cloud does), scope tokens minimally, and don’t paste write tokens into Grafana if read-only is enough.
