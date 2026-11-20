from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from bisect import bisect_right
from .checksums import CHECKSUMS, checksum
from .model import FrameModel, FrameRecord

@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    data: bytes
    checksum_ok: bool
    score: float

@dataclass(frozen=True)
class _RawCandidate:
    start: int
    end: int
    data: bytes
    body: bytes
    observed_checksum: int


def _sync_candidates(streams: list[bytes], limit: int = 8) -> list[bytes]:
    counts: Counter[bytes] = Counter()
    for stream in streams:
        counts.update(stream[i:i+2] for i in range(max(0, len(stream)-1)))
    # Constant fill bytes are common in idle regions and weak as sync evidence.
    ranked = [(n, token) for token, n in counts.items() if token not in (b"\x00\x00", b"\xff\xff")]
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [token for _, token in ranked[:limit]]


def _positions(data: bytes, needle: bytes):
    pos = data.find(needle)
    while pos >= 0:
        yield pos
        pos = data.find(needle, pos + 1)


def _scan(data: bytes, model: FrameModel, include_bad: bool = False) -> list[_Candidate]:
    out: list[_Candidate] = []
    for start in _positions(data, model.sync):
        lo = start + model.length_offset
        hi = lo + model.length_width
        if hi > len(data):
            continue
        length = int.from_bytes(data[lo:hi], model.length_endian)
        if length < 0 or length > model.max_payload:
            continue
        end = start + model.payload_offset + length + model.trailer_size
        if end > len(data) or end <= start:
            continue
        frame = data[start:end]
        body_end = end - model.trailer_size
        observed = int.from_bytes(data[body_end:end], "big")
        try:
            expected = checksum(data[start:body_end], model.checksum)
        except KeyError:
            continue
        ok = observed == expected
        if ok or include_bad:
            out.append(_Candidate(start, end, frame, ok, 10.0 if ok else 1.25))
    return out


def _select(candidates: list[_Candidate]) -> list[_Candidate]:
    """Weighted interval scheduling; valid checksums dominate suspect overlaps."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda c: (c.end, c.start, -c.score))
    ends = [c.end for c in ordered]
    dp = [0.0] * (len(ordered) + 1)
    take = [False] * len(ordered)
    prev = [0] * len(ordered)
    for i, cand in enumerate(ordered):
        p = bisect_right(ends, cand.start, 0, i)
        with_cand = dp[p] + cand.score
        without = dp[i]
        take[i] = with_cand > without
        prev[i] = p
        dp[i+1] = max(with_cand, without)
    chosen = []
    i = len(ordered)
    while i:
        if take[i-1] and dp[i] > dp[i-1]:
            chosen.append(ordered[i-1])
            i = prev[i-1]
        else:
            i -= 1
    return list(reversed(chosen))




def _scan_layout(data: bytes, sync: bytes, length_offset: int, length_width: int, length_endian: str, payload_offset: int, trailer_size: int, max_payload: int = 512) -> list[_RawCandidate]:
    out = []
    for start in _positions(data, sync):
        lo = start + length_offset
        hi = lo + length_width
        if hi > len(data):
            continue
        length = int.from_bytes(data[lo:hi], length_endian)
        if length < 0 or length > max_payload:
            continue
        end = start + payload_offset + length + trailer_size
        if end > len(data) or end <= start:
            continue
        body_end = end - trailer_size
        out.append(_RawCandidate(start, end, data[start:end], data[start:body_end], int.from_bytes(data[body_end:end], "big")))
    return out


def _stats_from_raw(raw_streams: list[list[_RawCandidate]], checksum_name: str, total_bytes: int) -> dict:
    selected = []
    all_candidates = []
    for sid, raw in enumerate(raw_streams):
        valid = []
        for c in raw:
            if checksum(c.body, checksum_name) == c.observed_checksum:
                valid.append(_Candidate(c.start, c.end, c.data, True, 10.0))
        chosen = _select(valid)
        all_candidates.extend(valid)
        selected.extend((sid, c) for c in chosen)
    raw_count = sum(len(stream) for stream in raw_streams)
    return {
        "count": len(selected),
        "coverage": sum(c.end-c.start for _, c in selected) / max(1, total_bytes),
        "length_diversity": len({c.end-c.start for _, c in selected}),
        "candidate_count": raw_count,
        "checksum_valid_candidates": len(all_candidates),
        "checksum_rate": len(all_candidates) / max(1, raw_count),
        "records": selected,
    }



def rank_hypotheses(
    training_streams: list[bytes],
    validation_streams: list[bytes],
    *,
    min_train_frames: int = 5,
    min_validation_frames: int = 4,
    min_validation_coverage: float = 0.08,
    min_checksum_rate: float = 0.70,
    sync_limit: int = 8,
) -> list:
    """Enumerate all scored hypotheses passing the train and validation gates.

    The search deliberately supports a bounded family: 2-byte sync, 1/2-byte
    length, 0..2 fixed bytes between length and payload, one-byte trailer, and
    the checksum functions in checksums.CHECKSUMS. Unknown families abstain.
    """
    if not training_streams or not validation_streams:
        return []
    syncs = _sync_candidates(training_streams, sync_limit)
    hypotheses = []
    for sync in syncs:
        for length_offset in range(2, 6):
            for width in (1, 2):
                for endian in (("little", "big") if width == 2 else ("little",)):
                    for extra in range(3):
                        payload_offset = length_offset + width + extra
                        layout_train = [_scan_layout(data, sync, length_offset, width, endian, payload_offset, 1) for data in training_streams]
                        layout_val = [_scan_layout(data, sync, length_offset, width, endian, payload_offset, 1) for data in validation_streams]
                        train_bytes = sum(map(len, training_streams))
                        val_bytes = sum(map(len, validation_streams))
                        for checksum_name in CHECKSUMS:
                            model = FrameModel(sync, length_offset, width, endian, payload_offset, 1, checksum_name)
                            train = _stats_from_raw(layout_train, checksum_name, train_bytes)
                            if train["count"] < min_train_frames or train["checksum_rate"] < min_checksum_rate:
                                continue
                            val = _stats_from_raw(layout_val, checksum_name, val_bytes)
                            if val["count"] < min_validation_frames or val["coverage"] < min_validation_coverage or val["checksum_rate"] < min_checksum_rate:
                                continue
                            score = (
                                2.0 * val["count"]
                                + 4.0 * val["coverage"]
                                + 3.0 * val["checksum_rate"]
                                + 0.25 * min(val["length_diversity"], 8)
                                + 0.02 * train["count"]
                            )
                            hypotheses.append((score, model, train, val))
    hypotheses.sort(key=lambda x: (-x[0], x[1].sync, x[1].length_offset, x[1].length_width, x[1].length_endian, x[1].payload_offset, x[1].checksum))
    return hypotheses


def infer_model(
    training_streams: list[bytes],
    validation_streams: list[bytes],
    *,
    min_train_frames: int = 5,
    min_validation_frames: int = 4,
    min_validation_coverage: float = 0.08,
    min_checksum_rate: float = 0.70,
    sync_limit: int = 8,
) -> dict:
    """Backward-compatible V0.2.1 single-model decision."""
    if not training_streams or not validation_streams:
        return {"status": "insufficient_data", "model": None, "candidates": []}
    hypotheses = rank_hypotheses(training_streams, validation_streams,
        min_train_frames=min_train_frames, min_validation_frames=min_validation_frames,
        min_validation_coverage=min_validation_coverage, min_checksum_rate=min_checksum_rate,
        sync_limit=sync_limit)
    if not hypotheses:
        return {"status": "rejected", "model": None, "candidates": []}
    # Collapse hypotheses that produce exactly the same validation boundaries.
    # Each structural/checksum combination is generated once. Keep all of them:
    # different models selecting the same boundaries can still be semantically
    # ambiguous. Avoid quadratic deduplication on noisy, unsupported streams.
    groups = []
    for item in hypotheses:
        signature = tuple((sid, c.start, c.end) for sid, c in item[3]["records"])
        groups.append(((signature, item[1]), item))
    best = groups[0][1]
    second_score = groups[1][1][0] if len(groups) > 1 else None
    # Distinct equally strong parses are an ambiguity, not a reason to guess.
    if second_score is not None and best[0] - second_score < 0.15:
        return {
            "status": "ambiguous",
            "model": None,
            "candidates": [g[1][1].to_dict() for g in groups[:5]],
        }
    return {
        "status": "accepted",
        "model": best[1],
        "training": {k: v for k, v in best[2].items() if k != "records"},
        "validation": {k: v for k, v in best[3].items() if k != "records"},
        "score": round(best[0], 4),
        "candidates": [g[1][1].to_dict() for g in groups[:5]],
    }


def decode_stream(data: bytes, model: FrameModel, stream_id: int = 0) -> dict:
    candidates = _scan(data, model, include_bad=True)
    valid = _select([c for c in candidates if c.checksum_ok])
    # A checksum-failed candidate is only retained as a suspect when it does not
    # overlap any accepted frame. It is never promoted to a trusted frame.
    suspects = [c for c in candidates if not c.checksum_ok and not any(c.start < v.end and v.start < c.end for v in valid)]
    suspects = _select(suspects)
    return {
        "frames": [FrameRecord(stream_id, c.start, c.end, c.data, True, "valid", c.score) for c in valid],
        "suspects": [FrameRecord(stream_id, c.start, c.end, c.data, False, "checksum_mismatch", c.score) for c in suspects],
    }
