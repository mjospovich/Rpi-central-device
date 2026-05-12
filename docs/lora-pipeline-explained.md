# LoRa Sensor Pipeline — Explained Simply

**Purpose:** This document explains how data from the DL-IAM LoRa sensor gets from the physical device all the way to InfluxDB Cloud. Written for clarity — no prior LoRa or IoT experience required.

---

## Table of Contents

1. [What We're Building](#1-what-were-building)
2. [The Big Picture](#2-the-big-picture)
3. [Step-by-Step: How Data Flows](#3-step-by-step-how-data-flows)
4. [Each Component Explained](#4-each-component-explained)
5. [The Network: Who Talks to Whom](#5-the-network-who-talks-to-whom)
6. [Troubleshooting: Where Did My Data Go?](#6-troubleshooting-where-did-my-data-go)
7. [Glossary](#7-glossary)

---

## 1. What We're Building

We have a **sensor** (DL-IAM) that measures:
- CO₂ (carbon dioxide)
- VOC (volatile organic compounds)
- Temperature and humidity
- Barometric pressure
- Light level
- Motion / presence (activity counter)

The sensor uses **LoRa** — a long-range, low-power radio technology. It doesn't use Wi‑Fi or Zigbee. It sends small packets of data over the air, and we need a **gateway** to receive those packets and forward them to our server.

**Goal:** Get the sensor's measurements into **InfluxDB Cloud** for dashboards (Grafana, Influx Data Explorer, etc.).

---

## 2. The Big Picture

Think of it like a postal system:

| Real-world analogy | Our system |
|--------------------|------------|
| You write a letter | Sensor measures CO₂, temp, etc. and encodes it |
| You put it in a mailbox | Sensor sends a LoRa radio packet |
| Post office picks it up | **Gateway** receives the radio packet |
| Post office sends it to sorting center | **Gateway** forwards via UDP to **ChirpStack Gateway Bridge** |
| Sorting center decodes address, routes letter | **ChirpStack** decodes the payload, publishes to **MQTT** |
| Letter arrives at destination | **Node-RED** + **Telegraf** land data in **InfluxDB Cloud** |

**In one sentence:** The sensor broadcasts data → the gateway hears it → the gateway sends it to ChirpStack → ChirpStack decodes it and puts it on MQTT → Node-RED reshapes it → Telegraf writes to **InfluxDB Cloud** (and you visualize with Grafana or the Influx UI).

---

## 3. Step-by-Step: How Data Flows

### Step 1: The Sensor Sends a Packet

- **Who:** DL-IAM sensor (battery or USB powered)
- **What:** Measures CO₂, temperature, humidity, etc.
- **How:** Encodes the values into a small binary payload (a few dozen bytes)
- **When:** Roughly every 1–2 minutes (configurable)
- **Where it goes:** The packet is broadcast over the air on LoRa frequencies (EU868: around 868 MHz)

**Important:** The sensor does NOT connect to Wi‑Fi. It only uses LoRa radio. It has no idea where our server is. It just broadcasts.

---

### Step 2: The Gateway Receives the Packet

- **Who:** Laird Sentrius RG186 (or similar LoRa gateway)
- **What:** Listens on LoRa frequencies. When it hears a packet, it captures it.
- **How:** Uses a LoRa radio chip. Receives the raw bytes + signal strength (RSSI), signal-to-noise (SNR)
- **Where it sends:** Forwards the packet to our Raspberry Pi over the **local network** using **UDP port 1700** (Semtech packet-forwarder protocol)

**Important:** The gateway must be on the same network as the Raspberry Pi. It's configured with the Pi's IP address (e.g. 192.168.1.149) and port 1700.

---

### Step 3: ChirpStack Gateway Bridge Receives the UDP Packet

- **Who:** `chirpstack-gateway-bridge` (Docker container on the Pi)
- **What:** Listens on UDP 1700. Receives the packet from the gateway.
- **How:** Converts the binary Semtech format to JSON and publishes to **MQTT** (Mosquitto)
- **MQTT topic:** `eu868/gateway/<gateway_id>/event/up`

**Important:** At this point, the payload is still **encoded** (raw bytes). ChirpStack doesn't know yet that it's CO₂ and temperature — it just sees bytes.

---

### Step 4: ChirpStack Processes the Packet

- **Who:** `chirpstack` (main LoRaWAN network server)
- **What:** Subscribes to gateway events on MQTT. When it sees an uplink:
  1. Checks if the device is registered (DevEUI, keys)
  2. If it's a **join request** (first time): responds with join-accept (OTAA)
  3. If it's **data**: runs the **payload decoder** (JavaScript) to turn bytes into readable values
  4. Publishes the decoded data to MQTT
- **MQTT topic (output):** `application/<app_id>/device/<dev_eui>/event/up`
- **Payload:** JSON with `object: { air_temperature: 21.5, co2_concentration: 534, ... }`

**Important:** The payload decoder is a small JavaScript function that knows the DL-IAM's binary format. Without it, we'd only see hex bytes.

---

### Step 5: Mosquitto — The Message Bus

- **Who:** `mosquitto` (MQTT broker)
- **What:** Central message hub. ChirpStack **publishes** application uplinks to it. Node-RED and Telegraf **subscribe**.
- **How:** MQTT pub/sub on port **1883** (host networking on the Pi).

---

### Step 6: Node-RED Normalizes the Payload

- **Who:** `nodered`
- **What:** Subscribes to `application/+/device/+/event/up`
- **How:** Extracts `object` and `deviceInfo`, builds flat JSON with a **measurement** name and **time_gmt2**, publishes to **`nodered/lorawan/<measurement>`** (and optionally **`nodered/lorawan_edge`** for certain naming patterns)

---

### Step 7: Telegraf Writes to InfluxDB Cloud

- **Who:** `telegraf`
- **What:** Subscribes to `nodered/lorawan/#` and `nodered/lorawan_edge`
- **How:** Parses JSON (measurement name + timestamp + tags/fields), writes via HTTPS to **InfluxDB Cloud** at **`INFLUX_URL`** into bucket **`INFLUX_BUCKET`**
- **Auth:** `INFLUX_TOKEN`, `INFLUX_ORG` in `.env`

---

### Step 8: Grafana or other tools (optional)

- **InfluxDB Cloud** web UI (**Data Explorer**) or **Grafana** with a Flux data source — query by measurement, `dev_eui`, or time range (use a read token in Grafana if you like).

---

## 4. Each Component Explained

### 4.1 DL-IAM Sensor

- **Device:** Decentlab DL-IAM (Indoor Ambiance Monitor)
- **DevEUI:** `70b3d57ba0001d9d` (unique ID, like a MAC address)
- **Activation:** OTAA (Over-The-Air Activation) — device joins the network by sending a join request; ChirpStack responds with join-accept and session keys
- **Region:** EU868 (European LoRa frequencies)

### 4.2 Laird Gateway

- **Model:** Sentrius RG186 (or RG1xx series)
- **Role:** Receives LoRa packets, forwards to network server via UDP
- **Config:** Semtech Forwarder mode, Pi IP + port 1700
- **Gateway ID (EUI):** `c0ee40ffff29847a` — used in MQTT topics

### 4.3 ChirpStack

- **Role:** LoRaWAN network server
- **Components:**
  - **Gateway Bridge:** UDP 1700 → MQTT (gateway events)
  - **ChirpStack:** Processes uplinks, runs payload decoder, publishes to MQTT
- **Payload decoder:** `chirpstack-decoders/DL-IAM.js` — converts binary → JSON

### 4.4 MQTT Topics (LoRa)

| Topic | Publisher | Subscribers |
|-------|-----------|-------------|
| `eu868/gateway/<id>/event/up` | Gateway Bridge | ChirpStack |
| `eu868/gateway/<id>/event/stats` | Gateway Bridge | ChirpStack |
| `application/<app_id>/device/<dev_eui>/event/up` | ChirpStack | Node-RED |

### 4.5 Node-RED Flow

- **Input:** `application/+/device/+/event/up`
- **Output:** `nodered/lorawan/<measurement>` (and optionally `nodered/lorawan_edge`)

### 4.6 Telegraf

- **Input:** `nodered/lorawan/#`, `nodered/lorawan_edge`
- **Output:** InfluxDB Cloud at `INFLUX_URL`, bucket `INFLUX_BUCKET`

---

## 5. The Network: Who Talks to Whom

```
              INTERNET (HTTPS)
                        │
                        ▼
              ┌─────────────────┐
              │ InfluxDB Cloud  │
              └────────▲─────────┘
                       │ Telegraf
                       │
    LOCAL NETWORK      │
    ┌──────────────────┼────────────────┐
    │                  │                │
    │  ┌─────────┐     │     ┌─────────┐│
    │  │ Gateway │─────┼────►│   Pi    ││
    │  │ (LoRa)  │ UDP │     │         ││
    │  │ 1700    │     │     │         ││
    │  └─────────┘     │     └────┬────┘│
    │                  │          │     │
    │                  │    ┌─────┴─────┐│
    │                  │    │ Mosquitto ││
    │                  │    │  1883     ││
    │                  │    └─────┬─────┘│
    │                  │          │     │
    │                  │   ChirpStack   │
    │                  │   Node-RED     │
    │                  │   Telegraf     │
    │                  │                │
    └──────────────────┼────────────────┘
                       │
    OVER THE AIR       │
    ┌──────────────────┼────────────────┐
    │  ┌─────────┐      │                │
    │  │ Sensor  │ LoRa │                │
    │  └─────────┘      │                │
    └───────────────────┴────────────────┘
```

**Summary:**
- **Sensor → Gateway:** LoRa radio (over the air)
- **Gateway → Pi:** UDP 1700 (local network)
- **ChirpStack, Node-RED, Telegraf:** On the Pi, using Mosquitto on localhost
- **Telegraf → InfluxDB Cloud:** HTTPS to `INFLUX_URL` (Pi needs outbound internet)

---

## 6. Troubleshooting: Where Did My Data Go?

### No data at all

| Check | Command / Action |
|-------|------------------|
| Is the gateway on the network? | Ping gateway IP / check router DHCP |
| Is the gateway forwarding to the Pi? | Gateway config: Pi IP, port 1700 |
| Is ChirpStack receiving? | `docker logs chirpstack 2>&1 \| grep -E "up\|70b3d57ba0001d9d"` |
| Is ChirpStack publishing to MQTT? | `docker exec mosquitto mosquitto_sub -t "application/#" -v` (wait 2–3 min) |
| Is data in InfluxDB Cloud? | Cloud UI → Data Explorer, or `mosquitto_sub -t 'nodered/lorawan/#' -v` then check Telegraf logs |

### MQTT: no application uplinks

Use `docker exec mosquitto mosquitto_sub -t "application/#" -v` and **wait** for an actual device transmission (often 1–3 minutes). Uplinks are sparse compared to a busy ZigBee broker.

### InfluxDB Cloud not receiving

- Check `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` in `.env`
- Confirm the token can **write** to that bucket in the Cloud UI
- Check Telegraf logs: `docker logs telegraf 2>&1 | tail -30`

---

## 7. Glossary

| Term | Meaning |
|------|---------|
| **LoRa** | Long-range, low-power radio technology for IoT |
| **LoRaWAN** | Protocol layer on top of LoRa (network, security, addressing) |
| **Gateway** | Device that receives LoRa packets and forwards them to a network server |
| **ChirpStack** | Open-source LoRaWAN network server |
| **DevEUI** | Unique 64-bit device identifier (like a MAC address) |
| **OTAA** | Over-The-Air Activation — device joins by sending join request; server responds with keys |
| **Uplink** | Message from device to network (sensor → gateway → server) |
| **Payload decoder** | Code that converts raw bytes into readable JSON (e.g. CO₂, temperature) |
| **MQTT** | Message broker protocol — publishers send to topics, subscribers receive |
| **Mosquitto** | MQTT broker software |
| **Semtech packet-forwarder** | Protocol used by gateways to send packets to a network server (UDP) |

---

*Rpi-central-device — LoRaWAN → InfluxDB Cloud. Edge repos that talk to this stack: [Related projects](related-projects.md).*
