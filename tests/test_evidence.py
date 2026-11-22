import unittest

from protocol_zero.evidence import (
    EvidenceSource, BoundarySeries, StructuralRule, FrameCandidate,
    candidates_from_decode, evaluate_candidate,
)


class EvidenceFusionTests(unittest.TestCase):
    def setUp(self):
        # Frame: sync(2), seq(1), payload_len(1), type(1), payload(7), CRC(1)
        self.frame = bytes([0xAA, 0x55, 0x03, 0x07, 0x10]) + b"PAYLOAD" + b"\x99"
        self.stream = b"\x00\x00" + self.frame + b"\xFF"
        self.start, self.end = 2, 2 + len(self.frame)
        self.candidate = FrameCandidate("s0", self.start, self.end, 2, 2, "crc")
        self.sources = [
            EvidenceSource("crc", "capture-1", "raw_capture"),
            EvidenceSource("uart", "logic-analyzer-1", "external_boundary"),
            EvidenceSource("spec", "protocol-spec-v1", "protocol_spec"),
        ]
        self.boundary = BoundarySeries("s0", "uart", 0, len(self.stream),
                                       (self.start, self.end))
        self.rules = [
            StructuralRule("sync", "spec", 0, 2, expected_values=(0xAA55,)),
            StructuralRule("payload-length", "spec", 3, 1, frame_length_delta=6),
            StructuralRule("message-type", "spec", 4, 1, expected_values=(0x10,)),
        ]

    def test_independent_boundary_and_spec_corroborate_crc(self):
        r = evaluate_candidate(self.candidate, {"s0": self.stream}, self.sources,
                               [self.boundary], self.rules)
        self.assertEqual(r["candidate_status"], "corroborated")
        self.assertEqual(r["independent_support_count"], 3)
        self.assertFalse(r["integrity_verified"])

    def test_same_origin_does_not_count_as_independent_sources(self):
        sources = [
            EvidenceSource("crc", "capture-1", "raw_capture"),
            EvidenceSource("uart", "capture-1", "external_boundary"),
            EvidenceSource("spec", "capture-1", "capture_derived"),
        ]
        rules = [StructuralRule("sync", "spec", 0, 2, expected_values=(0xAA55,))]
        r = evaluate_candidate(self.candidate, {"s0": self.stream}, sources,
                               [self.boundary], rules)
        self.assertEqual(r["candidate_status"], "single_source_supported")
        self.assertEqual(r["independent_support_count"], 1)

    def test_missing_boundary_inside_complete_coverage_is_conflict(self):
        bad = BoundarySeries("s0", "uart", 0, len(self.stream), (self.start,))
        r = evaluate_candidate(self.candidate, {"s0": self.stream}, self.sources,
                               [bad], self.rules)
        self.assertEqual(r["candidate_status"], "conflicted")
        self.assertEqual(r["contradicted_independence_groups"], ["logic-analyzer-1"])
        self.assertFalse(r["integrity_verified"])

    def test_boundary_outside_coverage_is_unknown_not_negative(self):
        partial = BoundarySeries("s0", "uart", self.start, self.start, (self.start,))
        r = evaluate_candidate(self.candidate, {"s0": self.stream}, self.sources,
                               [partial], [])
        self.assertEqual(r["candidate_status"], "single_source_supported")
        b = next(x for x in r["evidence"] if x["family"] == "external_boundary")
        self.assertEqual(b["end_boundary"], "unknown")

    def test_structural_mismatch_is_conflict(self):
        wrong = [StructuralRule("wrong-type", "spec", 4, 1, expected_values=(0x11,))]
        r = evaluate_candidate(self.candidate, {"s0": self.stream}, self.sources, [], wrong)
        self.assertEqual(r["candidate_status"], "conflicted")

    def test_crc_partial_vote_is_not_support(self):
        c = FrameCandidate("s0", self.start, self.end, 1, 2, "crc")
        r = evaluate_candidate(c, {"s0": self.stream}, self.sources, [], [])
        self.assertEqual(r["candidate_status"], "partial")
        self.assertFalse(r["crc_model_consensus"])

    def test_decode_adapter_preserves_agreed_and_contested(self):
        rows = candidates_from_decode("s0",
            {"agreed": [(2, 10)], "contested": [(12, 20, 1)]}, 2, "crc")
        self.assertEqual([(x.start, x.end, x.crc_votes) for x in rows],
                         [(2, 10, 2), (12, 20, 1)])
        self.assertEqual([x.crc_consensus for x in rows], [True, False])

    def test_invalid_source_kinds_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_candidate(self.candidate, {"s0": self.stream},
                [EvidenceSource("crc", "capture-1", "protocol_spec")], [], [])

    def test_rule_out_of_bounds_contradicts(self):
        rule = StructuralRule("missing", "spec", 99, 1, expected_values=(1,))
        r = evaluate_candidate(self.candidate, {"s0": self.stream}, self.sources, [], [rule])
        self.assertEqual(r["candidate_status"], "conflicted")
        self.assertIsNone(r["evidence"][1]["observed"])

    def test_no_evidence_remains_unresolved(self):
        c = FrameCandidate("s0", self.start, self.end)
        r = evaluate_candidate(c, {"s0": self.stream}, [], [], [])
        self.assertEqual(r["candidate_status"], "unresolved")
        self.assertFalse(r["integrity_verified"])

    def test_candidate_bounds_checked(self):
        with self.assertRaises(ValueError):
            evaluate_candidate(FrameCandidate("s0", 0, len(self.stream)+1),
                              {"s0": self.stream}, [], [], [])

    def test_boundary_coverage_cannot_exceed_stream(self):
        invalid = BoundarySeries("s0", "uart", 0, len(self.stream)+1,
                                 (self.start, self.end))
        with self.assertRaises(ValueError):
            evaluate_candidate(self.candidate, {"s0": self.stream}, self.sources,
                               [invalid], [])

    def test_decode_adapter_rejects_spans_without_models(self):
        with self.assertRaises(ValueError):
            candidates_from_decode("s0", {"agreed": [(2, 10)]}, 0, "")

    def test_crc_valid_false_span_is_rejected_by_independent_boundary(self):
        def crc8(data):
            value = 0
            for byte in data:
                value ^= byte
                for _ in range(8):
                    value = ((value << 1) ^ (0x07 if value & 0x80 else 0)) & 0xFF
            return value

        prefix = bytes([0xAA, 0x55, 0x03, 0x07, 0x10])
        payload = b"PAYLOAD"
        original_crc = crc8(prefix + payload)
        alternative_body = prefix + payload[:-1] + bytes([original_crc])
        padding = crc8(alternative_body)
        false_frame = alternative_body + bytes([padding])
        stream = b"\x00\x00" + false_frame + b"\xFF"
        start, false_end = 2, 2 + len(false_frame)
        actual_end = false_end - 1

        sources = [
            EvidenceSource("crc", "capture-1", "raw_capture"),
            EvidenceSource("uart", "logic-analyzer-1", "external_boundary"),
            EvidenceSource("spec", "protocol-spec-v1", "protocol_spec"),
        ]
        candidate = FrameCandidate("s0", start, false_end, 1, 1, "crc")
        boundary = BoundarySeries("s0", "uart", 0, len(stream),
                                  tuple(sorted((start, actual_end))))
        rules = [
            StructuralRule("sync", "spec", 0, 2, expected_values=(0xAA55,)),
            StructuralRule("payload-length", "spec", 3, 1, frame_length_delta=6),
            StructuralRule("type", "spec", 4, 1, expected_values=(0x10,)),
        ]
        result = evaluate_candidate(candidate, {"s0": stream}, sources, [boundary], rules)
        self.assertEqual(crc8(alternative_body), padding)
        self.assertEqual(result["candidate_status"], "conflicted")
        self.assertEqual(result["contradicted_independence_groups"], ["logic-analyzer-1"])
        self.assertFalse(result["integrity_verified"])


if __name__ == "__main__":
    unittest.main()
