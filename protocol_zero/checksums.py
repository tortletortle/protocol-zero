"""Small explicit checksum registry; unsupported algorithms must be rejected."""

def sum8(data: bytes) -> int:
    return sum(data) & 0xFF

def xor8(data: bytes) -> int:
    out = 0
    for value in data:
        out ^= value
    return out

def crc8(data: bytes, poly: int, init: int = 0, xorout: int = 0) -> int:
    value = init & 0xFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ (poly if value & 0x80 else 0)) & 0xFF
    return value ^ xorout

CHECKSUMS = {
    "sum8": sum8,
    "xor8": xor8,
    "crc8_smbus": lambda b: crc8(b, 0x07, 0x00, 0x00),
    "crc8_j1850": lambda b: crc8(b, 0x1D, 0xFF, 0xFF),
    "crc8_autosar": lambda b: crc8(b, 0x2F, 0xFF, 0xFF),
}

def checksum(data: bytes, name: str) -> int:
    return CHECKSUMS[name](data)
