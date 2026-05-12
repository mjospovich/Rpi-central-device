# Related edge projects

**Rpi-central-device** (this repo) is the **central LoRaWAN side**: ChirpStack (network server + gateway bridge), MQTT, Node-RED shaping, and Telegraf → **InfluxDB Cloud**. Field devices and companion stacks live in separate repos; they **join through your LoRa gateway** and are **managed in ChirpStack on this host**.

| Project | Role | How it ties to this stack |
|--------|------|---------------------------|
| [**LorBeePlugin**](https://github.com/mjospovich/LorBeePlugin) | Raspberry Pi Docker stack: **Zigbee2MQTT**, MQTT, Node-RED merges, plus a **LoRaWAN Class A end-device** for ChirpStack | Registers as a **device** in ChirpStack (OTAA). Uplinks hit the same gateway → **gateway bridge here** → decoded application payloads flow to MQTT and through **Node-RED / Telegraf** if you use this central pipeline. |
| [**Rpi-edge-alert**](https://github.com/mjospovich/Rpi-edge-alert) | Edge **air quality** (SPS30) + **environment** (BME680), Node-RED merge, optional **offline** calibration, **LoRaWAN v5** uplinks (ChirpStack-oriented device node) | Publishes merged sensor state locally; the **LoRa service** builds uplinks for your **network server**. Point device **keys / codec** at ChirpStack using this repo’s UI and (if needed) a payload decoder such as the one described in their [**docs**](https://github.com/mjospovich/Rpi-edge-alert/tree/main/docs). |

## Mental model

```text
[ LoRa field device / edge Pi ]  -- LoRa RF -->  [ Gateway ]  -- UDP 1700 -->  [ Gateway bridge + ChirpStack on THIS repo ]
                                                                                          |
                                                                                          v
                                                                                    MQTT → Node-RED → Telegraf → InfluxDB Cloud
```

You can run **central** (this repo) on one machine and **multiple** edge projects as separate nodes, each with its own DevEUI and application in ChirpStack.

## Docs on this side

- [**ChirpStack**](chirpstack.md) — applications, devices, integrations, MQTT topics  
- [**LoRa pipeline explained**](lora-pipeline-explained.md) — uplink path from radio to Influx  
- [**Gateway setup (Laird)**](gateway-setup-laird-rg1xx.md) — example commercial gateway aimed at this stack  

For **codec** and **payload layout** for Rpi-edge-alert, follow their **CHIRPSTACK** / **lora** documentation; for **LorBeePlugin**, follow that repo’s ChirpStack / device configuration docs.
