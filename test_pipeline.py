import unittest,random
from pipeline import analyze_pcaps,checksum
from evaluate_v19 import sample
from stream_framing import split

class Pipeline(unittest.TestCase):
    def test_vectors(self):
        self.assertEqual(checksum(b'123456789','CRC-8/SMBUS'),0xf4)
        self.assertEqual(checksum(bytes([1,2,3]),'SUM8'),6)
        self.assertEqual(checksum(bytes([1,2,3]),'XOR8'),0)
    def test_checksums(self):
        for kind in ('SUM8','XOR8','CRC-8/SMBUS'):
            r=random.Random(5); truth,a,p=sample(r,kind); _,b,q=sample(r,kind)
            result=analyze_pcaps([p],[q],502)
            self.assertTrue(any(kind in c['checksums'] and split(a,c['rules'][0])==truth for c in result['selected']))
    def test_unchecked(self):
        r=random.Random(5); _,_,p=sample(r,'no_checksum'); _,_,q=sample(r,'no_checksum')
        result=analyze_pcaps([p],[q],502)
        self.assertTrue(result['selected']); self.assertFalse(any(c['checksums'] for c in result['selected']))
    def test_bad_capture(self):
        from test_stream import pcap
        self.assertEqual(analyze_pcaps([pcap()],[pcap()])['status'],'unsupported_stream')
