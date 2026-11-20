from __future__ import annotations
from .checksums import checksum
from .model import FieldHypothesis, FrameModel, FrameRecord


def _counter_candidates(frames: list[bytes], offset: int, max_width: int = 4):
    out = []
    for width in (1, 2, 4):
        if width > max_width or any(len(f) < offset + width for f in frames):
            continue
        endians = ("little", "big") if width > 1 else ("little",)
        for endian in endians:
            values = [int.from_bytes(f[offset:offset+width], endian) for f in frames]
            mod = 1 << (8 * width)
            deltas = [((b-a) % mod) for a, b in zip(values, values[1:])]
            # Missing/corrupted frames can create sequence gaps. Keep such a
            # hypothesis, but distinguish it from exact unit-step evidence.
            rate = sum(1 <= delta <= 8 for delta in deltas) / max(1, len(deltas))
            if rate >= 0.95:
                unit_rate = sum(delta == 1 for delta in deltas) / max(1, len(deltas))
                out.append((width, endian, rate, values, unit_rate, deltas))
    return out


def infer_fields(records: list[FrameRecord], model: FrameModel) -> list[FieldHypothesis]:
    frames = [r.data for r in records if r.checksum_ok]
    if len(frames) < 3:
        return []
    fields: list[FieldHypothesis] = []
    fields.append(FieldHypothesis(0, len(model.sync), "sync", 1.0, ("identical sync bytes in accepted frames",)))
    fields.append(FieldHypothesis(model.length_offset, model.length_offset + model.length_width, "length", 1.0, ("value equals recovered variable payload length",)))
    fields.append(FieldHypothesis(-model.trailer_size, 0, "checksum", 1.0, (f"all accepted frames pass {model.checksum}",)))

    # Counter search is restricted to the fixed header region before payload.
    occupied = set(range(len(model.sync))) | set(range(model.length_offset, model.length_offset + model.length_width))
    for offset in range(len(model.sync), model.payload_offset):
        if offset in occupied:
            continue
        candidates = _counter_candidates(frames, offset)
        if not candidates:
            continue
        best = max(candidates, key=lambda x: (x[2], x[0]))
        width, endian, rate, values, unit_rate, deltas = best
        alternatives = tuple(f"{w}-byte {e}" for w, e, _, _, _, _ in candidates if (w, e) != (width, endian))
        has_carry = any((b >> 8) > (a >> 8) for a, b in zip(values, values[1:]))
        evidence = ("modular unit increment across accepted frames",) if unit_rate >= 0.95 else ("small positive modular steps; gaps may reflect dropped frames",)
        if alternatives and not has_carry:
            fields.append(FieldHypothesis(offset, offset + width, "counter_candidate_ambiguous", rate, evidence + ("wider interpretations remain observationally compatible",), alternatives))
        else:
            fields.append(FieldHypothesis(offset, offset + width, "counter_candidate", rate, evidence, alternatives))
        occupied.update(range(offset, offset + width))
        break

    # Classify remaining fixed-position bytes as constant or low-cardinality enum.
    max_fixed = min(model.payload_offset, min(map(len, frames)))
    for offset in range(len(model.sync), max_fixed):
        if offset in occupied:
            continue
        values = [f[offset] for f in frames]
        unique = sorted(set(values))
        if len(unique) == 1:
            fields.append(FieldHypothesis(offset, offset+1, "constant", 0.99, (f"one value across {len(frames)} frames",)))
        elif len(unique) <= 6:
            fields.append(FieldHypothesis(offset, offset+1, "enum_candidate", 0.8, (f"only {len(unique)} distinct values across {len(frames)} frames",)))

    # The payload boundary comes from the inferred length relation, not from
    # a semantic guess about the bytes inside it.
    fields.append(FieldHypothesis(model.payload_offset, -model.trailer_size, "payload", 0.95, ("variable span bounded by inferred length and trailer",)))
    fields.sort(key=lambda f: (f.start if f.start >= 0 else 10**6, f.end))
    return fields
