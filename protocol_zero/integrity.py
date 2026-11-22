"""Integrity evidence audit for CRC-based frame candidates.

CRC/model consensus is evidence of consistency with a bounded hypothesis family,
not proof that a captured frame was transmitted intact or is authentic.
"""
from __future__ import annotations


def crc_collision_baseline(checksum_bits: int = 8) -> dict:
    """Return the random-match baseline under an explicit uniformity assumption.

    This is not a calibrated false-positive probability for model selection,
    correlated hypotheses, structured padding, or real protocol traffic.
    """
    if type(checksum_bits) is not int or not 1 <= checksum_bits <= 64:
        raise ValueError("checksum_bits must be an integer from 1 to 64")
    return {
        "checksum_bits": checksum_bits,
        "uniform_random_false_match_baseline": 1 / (1 << checksum_bits),
        "assumption": (
            "candidate checksum is uniform and independent of covered bytes "
            "and of the model-selection process"
        ),
        "integrity_proof": False,
    }


def make_crc8_collision_witness(prefix: bytes, payload: bytes, model, delete_index: int) -> dict:
    """Construct two different histories with the exact same observed bytes.

    History A: one payload byte is deleted from an otherwise valid frame, then
    one padding byte follows. History B: the resulting bytes form a different
    clean frame whose payload includes the shifted original CRC byte.

    The caller must ensure prefix contains a header whose length field, if any,
    is consistent with len(payload). Model must expose predict(bytes) and
    return one CRC-8 byte. This demonstrates a limit; it is not a detector.
    """
    if not isinstance(prefix, bytes) or not isinstance(payload, bytes) or not payload:
        raise ValueError("byte prefix and nonempty payload required")
    if type(delete_index) is not int or not 0 <= delete_index < len(payload):
        raise ValueError("delete_index outside payload")
    predict = getattr(model, "predict", None)
    if not callable(predict):
        raise TypeError("model must provide predict(bytes)")

    original_body = prefix + payload
    original_crc = predict(original_body)
    if type(original_crc) is not int or not 0 <= original_crc <= 255:
        raise ValueError("model must produce one CRC-8 byte")

    shortened = payload[:delete_index] + payload[delete_index + 1:]
    alternative_body = prefix + shortened + bytes([original_crc])
    padding = predict(alternative_body)
    if type(padding) is not int or not 0 <= padding <= 255:
        raise ValueError("model must produce one CRC-8 byte")

    observed = alternative_body + bytes([padding])
    original_frame = original_body + bytes([original_crc])
    alternative_frame = alternative_body + bytes([padding])
    return {
        "observed_hex": observed.hex(),
        "original_clean_frame_hex": original_frame.hex(),
        "clean_alternative_frame_hex": alternative_frame.hex(),
        "deleted_payload_index": delete_index,
        "deleted_payload_byte": payload[delete_index],
        "original_crc": original_crc,
        "interframe_padding": padding,
        "original_clean_crc_valid": predict(original_body) == original_crc,
        "alternative_clean_crc_valid": predict(alternative_body) == padding,
        "same_observed_bytes": observed == alternative_frame,
        "interpretations": {
            "A": "original frame with one payload byte deleted, followed by one padding byte",
            "B": "a different clean frame whose payload includes the shifted original CRC byte",
        },
    }


def audit_decode(decoded: dict, model_count: int, checksum_bits: int = 8) -> dict:
    """Annotate joint_crc.decode output without promoting spans to verified data.

    decoded is expected to contain agreed pairs and contested triples
    (start, end, supporting_model_votes), as emitted by joint_crc.decode.
    """
    if not isinstance(decoded, dict):
        raise TypeError("decoded must be a mapping")
    if type(model_count) is not int or model_count < 0:
        raise ValueError("model_count must be a nonnegative integer")
    baseline = crc_collision_baseline(checksum_bits)
    agreed_input = decoded.get("agreed", [])
    contested_input = decoded.get("contested", [])
    if not isinstance(agreed_input, (list, tuple)) or not isinstance(contested_input, (list, tuple)):
        raise ValueError("agreed and contested must be sequences")
    if model_count == 0 and (agreed_input or contested_input):
        raise ValueError("spans cannot have votes when there are no active models")

    agreed = []
    for item in agreed_input:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("invalid agreed span")
        start, end = item
        if type(start) is not int or type(end) is not int or start < 0 or end <= start:
            raise ValueError("invalid agreed span")
        agreed.append({
            "start": start,
            "end": end,
            "consensus": "unanimous_within_active_models",
            "supporting_models": model_count,
            "active_models": model_count,
            "integrity_status": "unverified",
            "integrity_verified": False,
            "evidence": ["CRC/model consensus only"],
            "missing_independent_evidence": [
                "independent framing delimiter or boundary source",
                "independently validated payload invariant or stronger integrity field",
            ],
        })

    contested = []
    for item in contested_input:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise ValueError("invalid contested span")
        start, end, votes = item
        if (
            any(type(value) is not int for value in item)
            or start < 0
            or end <= start
            or not 0 <= votes <= model_count
        ):
            raise ValueError("invalid contested span")
        contested.append({
            "start": start,
            "end": end,
            "supporting_models": votes,
            "active_models": model_count,
            "consensus": "contested",
            "integrity_status": "unverified",
            "integrity_verified": False,
        })

    return {
        "status": "no_active_models" if model_count == 0 else "audited_candidates",
        "checksum": baseline,
        "agreed_candidates": agreed,
        "contested_candidates": contested,
        "policy": "No span is marked integrity_verified by CRC/model consensus alone.",
    }
