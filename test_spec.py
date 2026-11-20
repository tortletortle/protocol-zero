import unittest,json,random
from protocol_spec import export,load,decode
from pipeline import analyze
from evaluate_v20 import sample,crc_reference


def hypothesis(rule,checks=()):
    return dict(selected=True,rules=[rule],checksums=list(checks),observed_constants=[],length_fields=[])

class SpecTests(unittest.TestCase):
    def test_crc_reference(self): self.assertEqual(crc_reference(b'123456789'),0xf4)
    def test_roundtrip(self):
        r=random.Random(10); a,b,t=[sample(r,'CRC') for _ in range(3)]
        s=load(json.dumps(export(analyze([b''.join(a)],[b''.join(b)]))))
        out=decode(s,b''.join(t))
        self.assertEqual(out['status'],'checksum_verified')
        self.assertEqual(out['alternatives'][0]['frames'],[f.hex() for f in t])
    def test_invalid(self):
        for s in ({'version':2,'groups':[]},{'version':1,'groups':[hypothesis([0,3,'big',0])]},{'version':1,'groups':[hypothesis([0,1,'big',1],['bad'])]}):
            with self.assertRaises(ValueError): load(json.dumps(s))
    def test_alias_divergence(self):
        g=hypothesis([0,1,'big',1]); g['rules'].append([1,1,'big',1]); s=load(json.dumps(dict(version=1,groups=[g])))
        self.assertEqual(decode(s,bytes([3,1,3,1]))['status'],'ambiguous_boundaries')
    def test_checksum_cannot_switch_per_frame(self):
        s=load(json.dumps(dict(version=1,groups=[hypothesis([0,1,'big',1],['SUM8','XOR8'])])))
        # Same candidate must explain the whole stream; first SUM-only, next XOR-only.
        self.assertEqual(decode(s,bytes([3,3,1,7,3,3,1,1]))['status'],'checksum_rejected')
    def test_no_checksum(self):
        s=load(json.dumps(dict(version=1,groups=[hypothesis([0,1,'big',1])])))
        self.assertEqual(decode(s,b'\x02ab')['status'],'unverified')
        self.assertEqual(decode(s,b'\x02a')['status'],'no_framing')
    def test_empty(self): self.assertEqual(decode({'groups':[]},b'')['status'],'empty_input')
    def test_constants_not_semantics(self):
        g=hypothesis([0,1,'big',1]); g['observed_constants']=[[1,97]]
        s=load(json.dumps(dict(version=1,groups=[g])))
        r=decode(s,b'\x02bb'); self.assertEqual(r['status'],'unverified'); self.assertEqual(r['alternatives'][0]['hypotheses'][0]['constant_mismatches'],1)
