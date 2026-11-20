import unittest,struct
from stream_reassembly import assemble,streams
from stream_framing import infer,split


def packet(seq,body,flags=0,reverse=False):
    ip=bytearray(20); ip[0]=0x45; ip[2:4]=(40+len(body)).to_bytes(2,'big'); ip[9]=6
    ip[12:20]=bytes.fromhex('0a0000010a000002' if not reverse else '0a0000020a000001')
    tcp=bytearray(20); tcp[:8]=struct.pack('!HHI',*( (502,30000,seq) if reverse else (30000,502,seq)))
    tcp[12]=0x50; tcp[13]=flags
    p=bytes(12)+bytes.fromhex('0800')+ip+tcp+body
    return struct.pack('<IIII',0,0,len(p),len(p))+p


def pcap(*packets):
    return struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1)+b''.join(packets)

class StreamTests(unittest.TestCase):
    def test_reverse_and_duplicate(self):
        r=assemble([(103,b'def',False),(100,b'abc',False),(102,b'cd',False)])
        self.assertEqual((r['data'],r['duplicates']),(b'abcdef',2))
    def test_gap(self): self.assertEqual(assemble([(1,b'a',False),(3,b'c',False)])['status'],'gap')
    def test_conflict(self): self.assertEqual(assemble([(1,b'a',False),(1,b'b',False)])['status'],'conflict')
    def test_wrap(self): self.assertEqual(assemble([(0,b'cd',False),(2**32-2,b'ab',False)])['data'],b'abcd')
    def test_syn_gap(self): self.assertEqual(assemble([(10,b'',True),(11,b'x',False)])['status'],'gap')
    def test_multiple_syn(self): self.assertEqual(assemble([(10,b'',True),(20,b'',True)])['status'],'multiple_syn')
    def test_span(self): self.assertEqual(assemble([(1,b'x',False),(100,b'y',False)],10)['status'],'span_limit')
    def test_capture_directions(self):
        r=streams(pcap(packet(99,b'',2),packet(102,b'cd'),packet(100,b'ab'),packet(50,b'xyz',reverse=True)),502)
        self.assertEqual({x['data'] for x in r.values()},{b'abcd',b'xyz'})
    def test_framing(self):
        a=[bytes([n])+bytes(n) for n in range(5,17)]
        b=[bytes([n])+bytes(n) for n in range(10,22)]
        r=infer([b''.join(a)],[b''.join(b)])
        self.assertIn((0,1,'big',1),r); self.assertEqual(split(b''.join(b),(0,1,'big',1)),b)
    def test_truncated_frame(self): self.assertIsNone(split(b'\x05abc',(0,1,'big',1)))
