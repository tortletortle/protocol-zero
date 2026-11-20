import unittest
from protocol_zero.framing import infer_model, decode_stream
from protocol_zero.fields import infer_fields
from protocol_zero.synthetic import make_capture
from protocol_zero.checksums import checksum

class V02Tests(unittest.TestCase):
    def setUp(self):
        self.train = [make_capture(1000+i, 50, noise="clean").data for i in range(3)]
        self.validation = [make_capture(2000+i, 30, noise="clean").data for i in range(2)]

    def test_variable_length_and_unknown_stream_offset(self):
        fit = infer_model(self.train, self.validation)
        self.assertEqual(fit["status"], "accepted")
        m = fit["model"]
        self.assertEqual(m.sync, b"\xD5\x7E")
        self.assertEqual(m.length_offset, 3)
        self.assertEqual(m.payload_offset, 5)
        self.assertEqual(m.checksum, "crc8_smbus")

    def test_noisy_stream_resynchronizes_and_flags_corruption(self):
        fit = infer_model(self.train, self.validation)
        self.assertEqual(fit["status"], "accepted")
        test = make_capture(3001, 80, noise="noisy")
        decoded = decode_stream(test.data, fit["model"])
        self.assertGreaterEqual(len(decoded["frames"]), 45)
        self.assertGreaterEqual(len(decoded["suspects"]), 1)
        self.assertTrue(all(x.checksum_ok for x in decoded["frames"]))
        self.assertTrue(all(not x.checksum_ok for x in decoded["suspects"]))

    def test_field_recovery(self):
        fit = infer_model(self.train, self.validation)
        test = make_capture(4001, 60, noise="clean")
        decoded = decode_stream(test.data, fit["model"])
        fields = infer_fields(decoded["frames"], fit["model"])
        kinds = {f.kind for f in fields}
        self.assertIn("sync", kinds)
        self.assertIn("length", kinds)
        self.assertIn("payload", kinds)
        self.assertIn("checksum", kinds)
        self.assertTrue(any(f.kind.startswith("counter_candidate") for f in fields))
        encoded = {f.kind: f.to_dict() for f in fields}
        self.assertIsNone(encoded["payload"]["width"])
        self.assertEqual(encoded["checksum"]["width"], 1)

    def test_unknown_checksum_abstains(self):
        train = [make_capture(5000+i, 50, noise="clean", unknown_checksum=True).data for i in range(3)]
        val = [make_capture(6000+i, 30, noise="clean", unknown_checksum=True).data for i in range(2)]
        fit = infer_model(train, val)
        self.assertEqual(fit["status"], "rejected")
        self.assertIsNone(fit["model"])

    def test_combined_noise_retains_valid_frames(self):
        fit = infer_model(self.train, self.validation)
        test = make_capture(7001, 100, noise="combined")
        decoded = decode_stream(test.data, fit["model"])
        self.assertGreaterEqual(len(decoded["frames"]), 45)

    def test_two_byte_big_endian_length(self):
        def capture(seed, count):
            import random
            r = random.Random(seed)
            out = bytearray(r.randbytes(3))
            for seq in range(count):
                payload = r.randbytes(r.randrange(260, 320))
                body = b"\xA6\x39" + bytes([seq]) + len(payload).to_bytes(2, "big") + b"\x31" + payload
                out.extend(body + bytes([checksum(body, "crc8_smbus")]))
                out.extend(r.randbytes(r.randrange(0, 3)))
            return bytes(out)
        train = [capture(8000+i, 16) for i in range(3)]
        validation = [capture(8100+i, 10) for i in range(2)]
        fit = infer_model(train, validation)
        self.assertEqual(fit["status"], "accepted")
        self.assertEqual(fit["model"].sync, b"\xA6\x39")
        self.assertEqual(fit["model"].length_offset, 3)
        self.assertEqual(fit["model"].length_width, 2)
        self.assertEqual(fit["model"].length_endian, "big")
        self.assertEqual(fit["model"].payload_offset, 6)

    def test_empty_data_rejected(self):
        fit = infer_model([], [])
        self.assertEqual(fit["status"], "insufficient_data")

if __name__ == "__main__":
    unittest.main()
