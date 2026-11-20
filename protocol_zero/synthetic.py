from __future__ import annotations
import random
from dataclasses import dataclass
from .checksums import checksum, crc8

SYNC = b"\xD5\x7E"
CHECKSUM_NAME = "crc8_smbus"

@dataclass
class Capture:
    data: bytes
    truth: list[tuple[int, int]]
    corrupted_truth: list[tuple[int, int]]


def make_capture(seed: int, count: int, *, noise: str = "clean", unknown_checksum: bool = False) -> Capture:
    r = random.Random(seed)
    out = bytearray(r.randbytes(r.randrange(1, 7)))  # unknown initial stream offset
    truth: list[tuple[int, int]] = []
    corrupted: list[tuple[int, int]] = []
    seq = r.randrange(0, 256)
    for idx in range(count):
        payload_len = r.randrange(4, 31)
        payload = bytearray(r.randbytes(payload_len))
        if r.random() < 0.14 and payload_len >= 4:
            # A deliberate sync-word decoy inside payload.
            p = r.randrange(0, payload_len - 1)
            payload[p:p+2] = SYNC
        msg_type = r.choice((0x11, 0x11, 0x11, 0x24))
        body = SYNC + bytes([seq, payload_len, msg_type]) + bytes(payload)
        if unknown_checksum:
            check = crc8(body, 0x31, 0xA5, 0x5A)
        else:
            check = checksum(body, CHECKSUM_NAME)
        frame = bytearray(body + bytes([check]))
        is_corrupt = False
        if noise in ("noisy", "combined") and r.random() < 0.12:
            # Payload/checksum bit corruption; boundaries remain intact.
            p = r.randrange(5, len(frame))
            frame[p] ^= 1 << r.randrange(8)
            is_corrupt = True
        if noise == "combined" and r.random() < 0.025:
            # A byte deletion makes this frame structurally incomplete.
            p = r.randrange(5, len(frame))
            del frame[p]
            is_corrupt = True
        start = len(out)
        out.extend(frame)
        end = len(out)
        if is_corrupt:
            corrupted.append((start, end))
        else:
            truth.append((start, end))
        seq = (seq + 1) & 0xFF
        if noise in ("noisy", "combined", "shifted") and r.random() < 0.22:
            out.extend(r.randbytes(r.randrange(1, 5)))
        if noise == "combined" and r.random() < 0.015:
            out.extend(r.randbytes(r.randrange(1, 4)))
    return Capture(bytes(out), truth, corrupted)
