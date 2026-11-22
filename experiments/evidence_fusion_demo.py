"""Demonstrate boundary evidence rejecting a CRC-valid alternative span."""
import json
from pathlib import Path

from protocol_zero.crc_discovery import CRCModel
from protocol_zero.evidence import (
    BoundarySeries, EvidenceSource, FrameCandidate, StructuralRule,
    evaluate_candidate,
)


def run():
    model = CRCModel(0x07, 0, 0)
    prefix = bytes([0xAA, 0x55, 0x03, 0x07, 0x10])
    original_payload = b"PAYLOAD"
    original_crc = model.predict(prefix + original_payload)
    received_payload = original_payload[:-1]
    alternative_body = prefix + received_payload + bytes([original_crc])
    padding = model.predict(alternative_body)
    false_frame = alternative_body + bytes([padding])

    stream = b"\x00\x00" + false_frame + b"\xFF"
    start = 2
    false_end = start + len(false_frame)
    observed_end = false_end - 1
    sources = [
        EvidenceSource("crc-model", "capture-1", "raw_capture",
                       "CRC model evaluated over the captured byte stream"),
        EvidenceSource("uart-idle", "logic-analyzer-1", "external_boundary",
                       "independent receiver-side UART idle-gap measurement"),
        EvidenceSource("protocol-doc", "protocol-spec-v1", "protocol_spec",
                       "independently supplied frame-field constraints"),
    ]
    candidate = FrameCandidate("capture-0", start, false_end, 1, 1, "crc-model")
    boundaries = [BoundarySeries("capture-0", "uart-idle", 0, len(stream),
                                 tuple(sorted((start, observed_end))))]
    rules = [
        StructuralRule("sync", "protocol-doc", 0, 2, expected_values=(0xAA55,)),
        StructuralRule("payload-length", "protocol-doc", 3, 1,
                       frame_length_delta=6),
        StructuralRule("message-type", "protocol-doc", 4, 1,
                       expected_values=(0x10,)),
    ]
    result = evaluate_candidate(candidate, {"capture-0": stream}, sources,
                                boundaries, rules)
    return {
        "scenario": "one payload byte is deleted; the shifted original CRC and padding form a CRC-valid alternative span",
        "crc_model": {"poly": model.poly, "init": model.init, "xorout": model.xorout},
        "original_payload_hex": original_payload.hex(),
        "deleted_payload_byte_hex": original_payload[-1:].hex(),
        "original_crc_hex": f"{original_crc:02x}",
        "padding_hex": f"{padding:02x}",
        "observed_stream_hex": stream.hex(),
        "candidate_span": [start, false_end],
        "independently_observed_frame_end": observed_end,
        "result": result,
        "interpretation": (
            "The constructed alternative span passes the exact CRC-8 model and "
            "the length/type constraints. An independent UART boundary reports "
            "the end one byte earlier, so the fusion result is conflicted. "
            "This is a synthetic mechanism test, not a real-capture performance claim."
        ),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    Path("experiments/v027_evidence_fusion_demo.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
