from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class FrameModel:
    sync: bytes
    length_offset: int
    length_width: int
    length_endian: str
    payload_offset: int
    trailer_size: int
    checksum: str
    max_payload: int = 512

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sync"] = self.sync.hex(" ").upper()
        return d

@dataclass(frozen=True)
class FrameRecord:
    stream_id: int
    start: int
    end: int
    data: bytes
    checksum_ok: bool
    status: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "start": self.start,
            "end": self.end,
            "length": len(self.data),
            "data_hex": self.data.hex(" ").upper(),
            "checksum_ok": self.checksum_ok,
            "status": self.status,
            "score": round(self.score, 4),
        }

@dataclass(frozen=True)
class FieldHypothesis:
    start: int
    end: int
    kind: str
    confidence: float
    evidence: tuple[str, ...]
    alternatives: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "width": (self.end - self.start) if self.kind == "checksum" or (self.start >= 0 and self.end >= 0) else None,
            "kind": self.kind,
            "confidence": round(self.confidence, 4),
            "evidence": list(self.evidence),
            "alternatives": list(self.alternatives),
        }
