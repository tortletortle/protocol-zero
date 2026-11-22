"""Provenance-aware fusion of protocol-frame evidence.

Independence groups are declared provenance labels, not statistically proven
independence. Candidate agreement is never promoted to integrity proof.
"""
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

KINDS = {"raw_capture", "capture_derived", "external_boundary",
         "protocol_spec", "external_integrity", "operator_annotation"}


def _text(v, name):
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _int(v, name, minimum=0):
    if type(v) is not int or v < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    independence_group: str
    kind: str
    description: str = ""

    def __post_init__(self):
        _text(self.source_id, "source_id")
        _text(self.independence_group, "independence_group")
        if self.kind not in KINDS:
            raise ValueError(f"unsupported source kind: {self.kind}")
        if not isinstance(self.description, str):
            raise ValueError("description must be a string")


@dataclass(frozen=True)
class BoundarySeries:
    """Complete boundary detections over inclusive byte-offset coverage."""
    stream_id: str
    source_id: str
    covered_start: int
    covered_end: int
    boundaries: tuple[int, ...]

    def __post_init__(self):
        _text(self.stream_id, "stream_id")
        _text(self.source_id, "source_id")
        _int(self.covered_start, "covered_start")
        _int(self.covered_end, "covered_end")
        if self.covered_end < self.covered_start:
            raise ValueError("covered_end must be >= covered_start")
        if tuple(sorted(set(self.boundaries))) != tuple(self.boundaries):
            raise ValueError("boundaries must be sorted and unique")
        for x in self.boundaries:
            _int(x, "boundary")
            if not self.covered_start <= x <= self.covered_end:
                raise ValueError("boundary outside declared coverage")


@dataclass(frozen=True)
class StructuralRule:
    """A field constraint sourced from a protocol spec or capture derivation."""
    rule_id: str
    source_id: str
    offset: int
    width: int
    byteorder: str = "big"
    expected_values: tuple[int, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    frame_length_delta: int | None = None

    def __post_init__(self):
        _text(self.rule_id, "rule_id")
        _text(self.source_id, "source_id")
        _int(self.offset, "offset")
        _int(self.width, "width", 1)
        if self.width > 8 or self.byteorder not in ("big", "little"):
            raise ValueError("invalid field width or byte order")
        modes = (bool(self.expected_values),
                 self.minimum is not None or self.maximum is not None,
                 self.frame_length_delta is not None)
        if sum(modes) != 1:
            raise ValueError("exactly one expectation form is required")
        limit = (1 << (8 * self.width)) - 1
        if modes[1]:
            if self.minimum is None or self.maximum is None:
                raise ValueError("minimum and maximum must be supplied together")
            _int(self.minimum, "minimum")
            _int(self.maximum, "maximum")
            if self.maximum < self.minimum or self.maximum > limit:
                raise ValueError("invalid range for field width")
        if modes[2]:
            _int(self.frame_length_delta, "frame_length_delta")
        for value in self.expected_values:
            _int(value, "expected value")
            if value > limit:
                raise ValueError("expected value does not fit field width")


@dataclass(frozen=True)
class FrameCandidate:
    stream_id: str
    start: int
    end: int
    crc_votes: int = 0
    active_models: int = 0
    crc_source_id: str | None = None

    def __post_init__(self):
        _text(self.stream_id, "stream_id")
        _int(self.start, "start")
        _int(self.end, "end", 1)
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        _int(self.active_models, "active_models")
        _int(self.crc_votes, "crc_votes")
        if self.crc_votes > self.active_models:
            raise ValueError("crc_votes cannot exceed active_models")
        if self.active_models == 0 and self.crc_source_id is not None:
            raise ValueError("crc_source_id requires active CRC models")
        if self.active_models:
            _text(self.crc_source_id, "crc_source_id")

    @property
    def crc_consensus(self):
        return self.active_models > 0 and self.crc_votes == self.active_models


def candidates_from_decode(stream_id, decoded, active_models, crc_source_id):
    """Adapt joint_crc.decode output without losing partial model votes."""
    _text(stream_id, "stream_id")
    _int(active_models, "active_models")
    if active_models:
        _text(crc_source_id, "crc_source_id")
    if not isinstance(decoded, Mapping):
        raise TypeError("decoded must be a mapping")
    agreed, contested = decoded.get("agreed", []), decoded.get("contested", [])
    if not isinstance(agreed, (list, tuple)) or not isinstance(contested, (list, tuple)):
        raise ValueError("agreed and contested must be sequences")
    if active_models == 0 and (agreed or contested):
        raise ValueError("decoded spans cannot exist without active models")
    out = []
    for row in agreed:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError("invalid agreed span")
        out.append(FrameCandidate(stream_id, row[0], row[1], active_models,
                                  active_models, crc_source_id if active_models else None))
    for row in contested:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError("invalid contested span")
        out.append(FrameCandidate(stream_id, row[0], row[1], row[2], active_models,
                                  crc_source_id if active_models else None))
    return out


def _source_map(sources: Sequence[EvidenceSource]):
    result = {}
    for source in sources:
        if not isinstance(source, EvidenceSource):
            raise TypeError("sources must contain EvidenceSource objects")
        if source.source_id in result and result[source.source_id] != source:
            raise ValueError(f"conflicting source definition: {source.source_id}")
        result[source.source_id] = source
    return result


def _edge(offset, series):
    if not series.covered_start <= offset <= series.covered_end:
        return "unknown"
    return "supported" if offset in series.boundaries else "contradicted"


def _check_rule(rule, frame):
    end = rule.offset + rule.width
    if end > len(frame):
        return {"status": "contradicted", "observed": None,
                "expected": "field_present", "detail": "required field exceeds frame"}
    value = int.from_bytes(frame[rule.offset:end], rule.byteorder)
    if rule.expected_values:
        expected, ok = list(rule.expected_values), value in rule.expected_values
    elif rule.frame_length_delta is not None:
        expected = len(frame) - rule.frame_length_delta
        ok = expected >= 0 and value == expected
    else:
        expected, ok = [rule.minimum, rule.maximum], rule.minimum <= value <= rule.maximum
    return {"status": "supported" if ok else "contradicted", "observed": value,
            "expected": expected,
            "detail": "field satisfies constraint" if ok else "field violates constraint"}


def evaluate_candidate(candidate: FrameCandidate, streams: Mapping[str, bytes],
                       sources: Sequence[EvidenceSource], boundary_series=(),
                       structural_rules=()):
    """Evaluate a candidate while preserving provenance and contradictions."""
    if not isinstance(candidate, FrameCandidate):
        raise TypeError("candidate must be a FrameCandidate")
    if candidate.stream_id not in streams:
        raise ValueError(f"missing stream: {candidate.stream_id}")
    stream = streams[candidate.stream_id]
    if not isinstance(stream, bytes):
        raise TypeError("stream values must be bytes")
    if candidate.end > len(stream):
        raise ValueError("candidate span exceeds stream")
    source_by_id = _source_map(sources)
    frame = stream[candidate.start:candidate.end]
    evidence = []

    if candidate.active_models:
        source = source_by_id.get(candidate.crc_source_id)
        if source is None or source.kind != "raw_capture":
            raise ValueError("CRC consensus must reference a raw_capture source")
        evidence.append({
            "family": "crc_model_consensus", "source_id": source.source_id,
            "independence_group": source.independence_group,
            "status": "supported" if candidate.crc_consensus else "partial",
            "detail": f"{candidate.crc_votes}/{candidate.active_models} active models agree",
            "counts_as_integrity_proof": False,
        })

    seen_series = set()
    for series in boundary_series:
        if not isinstance(series, BoundarySeries):
            raise TypeError("boundary_series must contain BoundarySeries objects")
        if series.stream_id != candidate.stream_id:
            continue
        if series.covered_end > len(stream):
            raise ValueError("boundary coverage exceeds stream length")
        source = source_by_id.get(series.source_id)
        if source is None or source.kind != "external_boundary":
            raise ValueError("boundary series must reference external_boundary source")
        key = (series.stream_id, series.source_id)
        if key in seen_series:
            raise ValueError("duplicate boundary series for source and stream")
        seen_series.add(key)
        start_state, end_state = _edge(candidate.start, series), _edge(candidate.end, series)
        states = (start_state, end_state)
        if "contradicted" in states:
            status = "contradicted"
        elif states == ("supported", "supported"):
            status = "supported"
        elif "supported" in states:
            status = "partial"
        else:
            status = "unknown"
        evidence.append({
            "family": "external_boundary", "source_id": source.source_id,
            "independence_group": source.independence_group, "status": status,
            "start_boundary": start_state, "end_boundary": end_state,
            "detail": "positions checked against declared complete coverage",
            "counts_as_integrity_proof": False,
        })

    seen_rules = set()
    for rule in structural_rules:
        if not isinstance(rule, StructuralRule):
            raise TypeError("structural_rules must contain StructuralRule objects")
        source = source_by_id.get(rule.source_id)
        if source is None or source.kind not in ("protocol_spec", "capture_derived"):
            raise ValueError("structural rules require protocol_spec or capture_derived source")
        if rule.rule_id in seen_rules:
            raise ValueError(f"duplicate structural rule id: {rule.rule_id}")
        seen_rules.add(rule.rule_id)
        evidence.append({
            "family": "structural_constraint", "rule_id": rule.rule_id,
            "source_id": source.source_id, "independence_group": source.independence_group,
            **_check_rule(rule, frame), "counts_as_integrity_proof": False,
        })

    grouped = {}
    for item in evidence:
        grouped.setdefault(item["independence_group"], []).append(item["status"])
    group_results = []
    for group, statuses in sorted(grouped.items()):
        if "contradicted" in statuses:
            state = "contradicted"
        elif "supported" in statuses:
            state = "supported"
        elif "partial" in statuses:
            state = "partial"
        else:
            state = "unknown"
        group_results.append({"independence_group": group, "status": state,
                              "evidence_items": len(statuses)})
    supporting = [x["independence_group"] for x in group_results if x["status"] == "supported"]
    contradicted = [x["independence_group"] for x in group_results if x["status"] == "contradicted"]
    partial = [x["independence_group"] for x in group_results if x["status"] == "partial"]
    if contradicted:
        status = "conflicted"
    elif len(supporting) >= 2:
        status = "corroborated"
    elif len(supporting) == 1:
        status = "single_source_supported"
    elif partial:
        status = "partial"
    else:
        status = "unresolved"

    return {
        "candidate": {"stream_id": candidate.stream_id, "start": candidate.start,
                      "end": candidate.end, "length": candidate.end - candidate.start},
        "candidate_status": status, "crc_model_consensus": candidate.crc_consensus,
        "evidence": evidence, "evidence_groups": group_results,
        "supporting_independence_groups": supporting,
        "contradicted_independence_groups": contradicted,
        "partial_independence_groups": partial,
        "independent_support_count": len(supporting), "integrity_verified": False,
        "independence_basis": (
            "user-declared provenance groups only; statistical independence "
            "and source authenticity are not established"
        ),
    }


def fuse_candidates(candidates: Iterable[FrameCandidate], streams: Mapping[str, bytes],
                    sources: Sequence[EvidenceSource], boundary_series=(),
                    structural_rules=()):
    """Evaluate multiple candidates with the same declared evidence set."""
    return [evaluate_candidate(c, streams, sources, boundary_series, structural_rules)
            for c in candidates]
