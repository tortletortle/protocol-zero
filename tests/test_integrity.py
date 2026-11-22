import unittest

from protocol_zero.crc_discovery import CRCModel
from protocol_zero.integrity import (
    audit_decode,
    crc_collision_baseline,
    make_crc8_collision_witness,
)


class IntegrityAuditTests(unittest.TestCase):
    def setUp(self):
        self.model = CRCModel(0x07, 0, 0)

    def test_constructive_collision_has_identical_observation(self):
        # sync, sequence, one-byte length, message type
        prefix = bytes([0xAA, 0x55, 0x04, 0x10, 0x20])
        payload = bytes(range(1, 17))
        witness = make_crc8_collision_witness(prefix, payload, self.model, 5)
        self.assertTrue(witness["original_clean_crc_valid"])
        self.assertTrue(witness["alternative_clean_crc_valid"])
        self.assertTrue(witness["same_observed_bytes"])
        self.assertEqual(witness["observed_hex"], witness["clean_alternative_frame_hex"])
        self.assertNotEqual(witness["observed_hex"], witness["original_clean_frame_hex"])
        self.assertEqual(witness["deleted_payload_byte"], 6)

    def test_agreed_spans_never_promoted_to_verified(self):
        result = audit_decode({"agreed": [(1005, 1045)], "contested": []}, 3)
        candidate = result["agreed_candidates"][0]
        self.assertEqual(candidate["integrity_status"], "unverified")
        self.assertFalse(candidate["integrity_verified"])
        self.assertEqual(candidate["supporting_models"], 3)

    def test_contested_spans_remain_contested(self):
        result = audit_decode({"agreed": [], "contested": [(10, 20, 1)]}, 2)
        candidate = result["contested_candidates"][0]
        self.assertEqual(candidate["consensus"], "contested")
        self.assertFalse(candidate["integrity_verified"])

    def test_uniform_random_match_baseline(self):
        self.assertEqual(
            crc_collision_baseline(8)["uniform_random_false_match_baseline"], 1 / 256
        )
        self.assertEqual(
            crc_collision_baseline(16)["uniform_random_false_match_baseline"], 1 / 65536
        )
        self.assertFalse(crc_collision_baseline(8)["integrity_proof"])

    def test_bad_checksum_width_rejected(self):
        for bits in (0, 65, True, 8.0):
            with self.subTest(bits=bits), self.assertRaises(ValueError):
                crc_collision_baseline(bits)

    def test_bad_spans_rejected(self):
        with self.assertRaises(ValueError):
            audit_decode({"agreed": [(10, 10)]}, 1)
        with self.assertRaises(ValueError):
            audit_decode({"contested": [(1, 2, 3)]}, 2)
        with self.assertRaises(ValueError):
            audit_decode({"agreed": [(1, 2)]}, 0)

    def test_bad_witness_input_rejected(self):
        with self.assertRaises(ValueError):
            make_crc8_collision_witness(b"H", b"", self.model, 0)
        with self.assertRaises(ValueError):
            make_crc8_collision_witness(b"H", b"abc", self.model, 3)


if __name__ == "__main__":
    unittest.main()
