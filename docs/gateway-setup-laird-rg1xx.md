# Laird Sentrius RG1xx Gateway Setup Guide

**Gateway:** Laird Sentrius RG1xx LoRaWAN Gateway  
**Network server:** ChirpStack (this repository’s Docker stack, or any ChirpStack install you point the gateway at)  
**Use case:** Point a Semtech packet-forwarder gateway at this host’s UDP **1700** → ChirpStack (e.g. DL-IAM / EU868 in the original write-up; same pattern for other devices registered in ChirpStack)

---

## Prerequisites

- [x] ChirpStack running (`chirpstack`, `chirpstack-gateway-bridge` containers up)
- [x] DL-IAM device registered in ChirpStack with OTAA keys
- [ ] Laird Sentrius RG1xx gateway powered and on same network as Raspberry Pi

---

## Step 1: Find Your Raspberry Pi IP

The gateway needs to send packets to your ChirpStack Gateway Bridge. Use the Pi's IP or hostname:

```bash
# On the Raspberry Pi
hostname -I | awk '{print $1}'
# or use hostname if DNS resolves:
hostname
# e.g. raspberrypi
```

**Note:** Use a literal IP (e.g. `192.168.1.42`) if the hostname does not resolve from the gateway’s network.

---

## Step 2: Access the Laird Gateway Web Interface

1. **Find the gateway on the network**
   - Default: gateway uses DHCP. Check your router's DHCP client list, or
   - Use mDNS: `https://rg1xxXXXXXX.local` (XXXXXX = last 6 chars of Ethernet MAC, on label)

2. **Open in browser**
   - `https://rg1xxXXXXXX.local` or `https://<gateway-ip>`
   - Accept the self-signed certificate (Advanced → Proceed)

3. **Log in**
   - **Username:** `sentrius`
   - **Password:** `RG1xx`
   - *(Change password later under Wi-Fi → Advanced)*

---

## Step 3: Configure Semtech Forwarder

ChirpStack Gateway Bridge listens on **UDP 1700**. Configure the Laird to send packets there.

1. In the left menu: **Forwarder**
2. In the top bar: **LoRa**
3. **Mode:** Select **Semtech Forwarder**
4. **Network Server Address:** Enter your ChirpStack host IP (e.g. `192.168.1.42` or a LAN DNS name if it resolves from the gateway)
5. **Port:** `1700` (Semtech packet-forwarder default; ChirpStack uses 1700 for EU868)
6. Save / Apply

---

## Step 4: Get the Gateway ID (EUI)

You need the gateway's EUI to register it in ChirpStack.

- **Where to find it:** Often on the gateway label, or in the web UI under **LoRa** or **Gateway** settings
- **Format:** 16 hex characters, e.g. `b827ebfffe123456`
- If unsure: check the gateway's MAC address — the EUI is usually derived from it (e.g. `b827ebffff` + last 6 of MAC)

---

## Step 5: Register Gateway in ChirpStack

1. Open **`http://<chirpstack-host>:8081`**
2. Go to your tenant (e.g. **test-martin**)
3. **Gateways** → **Add gateway**
4. Fill in:
   - **Name:** e.g. `Laird RG1xx Lab`
   - **Gateway ID (EUI):** The 16-char hex from Step 4 (e.g. `b827ebfffe123456`)
   - **Region:** `EU868`
5. Submit

---

## Step 6: Verify Connection

1. **ChirpStack UI** → **Gateways** → your gateway
   - **Last seen** should update within a minute if the gateway is sending
   - **Status** may show "Never seen" until the gateway sends its first packet

2. **Gateway web UI**
   - Look for connection status / green indicators
   - Some firmware shows "Connected" or similar when packets are accepted

3. **Docker logs** (optional)
   ```bash
   docker logs chirpstack-gateway-bridge 2>&1 | tail -20
   ```
   You should see activity when the gateway sends packets.

---

## Step 7: Power the DL-IAM Sensor

1. Power the DL-IAM (battery or USB)
2. Place it within range of the gateway (indoors: a few meters to tens of meters depending on walls)
3. The sensor will send a **join request** (OTAA)
4. ChirpStack will respond with **join-accept** (if keys match)

**In ChirpStack:**
- **Devices** → **DL-IAM Lab** → **Activation** tab: should show "Activated" after join
- **LoRaWAN frames** tab: uplinks with decoded payload (CO2, VOC, temperature, etc.)

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| Gateway "Never seen" in ChirpStack | Gateway and Pi on same network? Firewall allows UDP 1700? Correct IP in gateway config? |
| DL-IAM doesn't activate | AppEUI/AppKey match in ChirpStack and sensor? Sensor in range? Gateway receiving? |
| No decoded payload | Device profile has DL-IAM decoder? Check LoRaWAN frames — is raw payload present? |
| Gateway can't reach Pi | Use Pi's IP instead of hostname. Ensure no firewall blocking UDP 1700. |

### Firewall (if enabled)

```bash
# Allow ChirpStack gateway traffic (UDP 1700)
sudo ufw allow 1700/udp
sudo ufw reload
```

---

## Quick Reference

| Item | Value |
|------|-------|
| ChirpStack Gateway Bridge | UDP 1700 |
| Laird mode | Semtech Forwarder |
| Laird default login | sentrius / RG1xx |
| ChirpStack UI | `http://<chirpstack-host>:8081` |
| Region | EU868 |

---

*ChirpStack + Laird Sentrius RG1xx; example device: Decentlab DL-IAM (EU868).*
