import unittest,struct
from capture import payloads
from length_rules import infer


def fixture(body):
    eth=b'\0'*12+b'\x08\x00'
    ip=bytearray(20); ip[0]=0x45; ip[2:4]=(40+len(body)).to_bytes(2,'big'); ip[9]=6
    tcp=bytearray(20); tcp[:4]=struct.pack('!HH',30000,502); tcp[12]=0x50
    p=eth+ip+tcp+body
    return struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1)+struct.pack('<IIII',0,0,len(p),len(p))+p

class Capture(unittest.TestCase):
    def test_payload(self): self.assertEqual(list(payloads(fixture(b'abc'),502)),[b'abc'])
    def test_filter(self): self.assertEqual(list(payloads(fixture(b'abc'),80)),[])
    def test_truncated(self):
        with self.assertRaises(ValueError): list(payloads(fixture(b'abc')[:-1]))
    def test_ambiguity(self):
        r=[bytes([0,n])+bytes(n) for n in range(5,25)]
        self.assertIn(dict(offset=0,width=2,endian='big',bias=2),infer(r[:10],r[10:])['rules'])
        self.assertIn(dict(offset=1,width=1,endian='big',bias=2),infer(r[:10],r[10:])['rules'])
    def test_fixed(self): self.assertEqual(infer([b'ab']*10,[b'ab']*10)['status'],'insufficient_variation')
