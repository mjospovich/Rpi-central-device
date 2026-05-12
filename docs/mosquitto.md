# Mosquitto

**Service:** `mosquitto`  
**Image:** `eclipse-mosquitto:latest`  
**Network:** `host`

## Overview

Mosquitto is the MQTT broker for this stack. **ChirpStack** (via the gateway bridge and application integration), **Node-RED**, and **Telegraf** all use `localhost:1883` because of host networking.

## How it works

- Listener on **1883**.
- Persistence under `./mosquitto/data` (gitignored at runtime).
- `allow_anonymous true` in the committed config — suitable for a trusted LAN; use passwords and ACLs for production.

## Files

| Path | Purpose |
|------|---------|
| `mosquitto/config/mosquitto.conf` | Broker configuration |
| `mosquitto/data/` | Persistence (created by the container) |

## Topic summary

| Pattern | Typical publisher | Consumers |
|---------|-------------------|-----------|
| `<region>/gateway/<id>/event/*` | Gateway bridge | ChirpStack |
| `application/+/device/+/event/up` | ChirpStack | Node-RED |
| `nodered/lorawan/#`, `nodered/lorawan_edge` | Node-RED | Telegraf |

## Debugging

```bash
docker exec mosquitto mosquitto_sub -t 'application/#' -v
docker exec mosquitto mosquitto_sub -t 'nodered/lorawan/#' -v
```

## Dependencies

None. Start Mosquitto before or with ChirpStack, Node-RED, and Telegraf.
