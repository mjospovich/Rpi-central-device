"""Decentlab-style downlink encoding (DL-IAM and similar).

Frame format matches https://decentlab.github.io/decentlab-decoders/downlink-command-encoder.html :
  payload = <4 hex opcode><4 hex u16 parameter>
  cmd     = payload + <4 hex CRC-16>  (CRC over payload bytes, algorithm as on that page)
"""

from __future__ import annotations

from base64 import b64encode

# Subset of commands exposed in the dashboard (see Decentlab encoder for full list).
# Keys are 4-char uppercase hex opcodes.
DECENTLAB_UI_COMMANDS: tuple[dict[str, object], ...] = (
    {
        "opcode": "0001",
        "name": "Set sampling period (seconds)",
        "save": False,
        "param_min": 1,
        "param_max": 65535,
        "min_firmware": "0.2.7",
    },
    {
        "opcode": "0002",
        "name": "Set sampling period + save",
        "save": True,
        "param_min": 1,
        "param_max": 65535,
        "min_firmware": "0.2.7",
    },
    {
        "opcode": "0011",
        "name": "Set send period (samples per uplink)",
        "save": False,
        "param_min": 0,
        "param_max": 65535,
        "min_firmware": "1.4.0",
    },
    {
        "opcode": "0012",
        "name": "Set send period + save",
        "save": True,
        "param_min": 0,
        "param_max": 65535,
        "min_firmware": "1.4.0",
    },
    {
        "opcode": "0003",
        "name": "Set default Tx data rate (DR)",
        "save": False,
        "param_min": 0,
        "param_max": 15,
        "min_firmware": "0.2.7",
    },
    {
        "opcode": "0004",
        "name": "Set default Tx data rate + save",
        "save": True,
        "param_min": 0,
        "param_max": 15,
        "min_firmware": "0.2.7",
    },
)

ALLOWED_DL_OPCODES = frozenset(str(c["opcode"]) for c in DECENTLAB_UI_COMMANDS)


def crc16_decentlab(hex_payload: str) -> int:
    """CRC-16 over payload interpreted as byte pairs (same as Decentlab HTML tool)."""
    crc = 0xFFFF
    for i in range(0, len(hex_payload), 2):
        b = int(hex_payload[i : i + 2], 16)
        crc ^= b
        for _ in range(8):
            odd = crc & 0x0001
            crc >>= 1
            if odd:
                crc ^= 0xA001
    return crc & 0xFFFF


def build_decentlab_hex(opcode: str, param: int) -> str:
    """Return 12 uppercase hex chars: 2B opcode + 2B param + 2B CRC."""
    op = "".join(c for c in opcode.upper() if c in "0123456789ABCDEF")
    if len(op) != 4:
        raise ValueError("opcode must be 4 hex characters")
    if op not in ALLOWED_DL_OPCODES:
        raise ValueError("unsupported Decentlab opcode")
    p = int(param) & 0xFFFF
    payload = op + f"{p:04X}"
    crc = crc16_decentlab(payload)
    return (payload + f"{crc:04X}").upper()


def decentlab_hex_to_b64(hex_cmd: str) -> str:
    return b64encode(bytes.fromhex(hex_cmd)).decode()
