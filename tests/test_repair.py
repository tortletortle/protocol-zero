import unittest, random
from protocol_zero.repair import candidates, repair_stream, learn_profiles, Profile
from protocol_zero.model import FrameModel
from protocol_zero.checksums import checksum, CHECKSUMS
from protocol_zero.framing import decode_stream
from protocol_zero.pipeline import analyze

def pack(p,m):
    b=m.sync+bytes([len(p)])+p
    return b+bytes([checksum(b,m.checksum)])

def brute(obs,m):
    body=obs[:-1];p=m.payload_offset;target=obs[-1];n=obs[m.length_offset];delta=len(obs)-p-n-1
    out=set()
    def add(b):
        if checksum(b,m.checksum)==target:out.add(b+obs[-1:])
    if delta==-1:
        for i in range(p,len(body)+1):
            for v in range(256):add(body[:i]+bytes([v])+body[i:])
    if delta==1:
        for i in range(p,len(body)):add(body[:i]+body[i+1:])
    if delta==0 and checksum(body,m.checksum)!=target:
        for i in range(p,len(body)):
            for bit in range(8):add(body[:i]+bytes([body[i]^(1<<bit)])+body[i+1:])
    return sorted(out)

class RepairTests(unittest.TestCase):
    def test_matches_exhaustive_oracle(self):
        r=random.Random(73211)
        for name in CHECKSUMS:
            m=FrameModel(b'\xb8\x34',2,1,'little',3,1,name)
            for _ in range(8):
                q=pack(r.randbytes(r.randrange(3,11)),m);i=r.randrange(3,len(q)-1)
                for obs in [q[:i]+q[i+1:],q[:i]+b'\xa3'+q[i:],q[:i]+bytes([q[i]^8])+q[i+1:]]:
                    with self.subTest(name=name,obs=obs.hex()):
                        self.assertEqual(candidates(obs,m)[1],brute(obs,m));self.assertIn(q,candidates(obs,m)[1])
    def test_ambiguous_deleted_byte(self):
        m=FrameModel(b'\xb8\x34',2,1,'little',3,1,'xor8');q=pack(b'abcdef',m)
        obs=q[:5]+q[6:];kind,cs=candidates(obs,m)
        self.assertEqual(kind,'missing_byte');self.assertGreater(len(cs),1);self.assertIn(q,cs)
    def test_unique_profile_not_trusted(self):
        m=FrameModel(b'\xb8\x34',2,1,'little',3,1,'sum8')
        q=pack(b'\x01\x02\x03\x04',m);a=pack(b'\x10\x20',m);b=pack(b'\x20\x30',m)
        obs=q[:4]+b'\xf9'+q[4:];raw=a+obs+b
        before=decode_stream(raw,m);row=repair_stream(raw,m,{},decoded=before)[0]
        self.assertEqual(row['proposed_hex'],q.hex());self.assertFalse(row['trusted']);self.assertEqual(len(before['frames']),2)
    def test_profile_requires_independent_validation(self):
        m=FrameModel(b'\xb8\x34',2,1,'little',3,1,'xor8')
        a=b''.join(pack(bytes([1,i]),m) for i in range(20));b=b''.join(pack(bytes([2,i]),m) for i in range(20,40));c=b''.join(pack(bytes([1,i]),m) for i in range(20,40))
        self.assertNotIn(2,learn_profiles([a],[b],m));self.assertEqual(learn_profiles([a],[c],m)[2].constants,((0,1),))
    def test_profile_conflict(self):
        m=FrameModel(b'\xb8\x34',2,1,'little',3,1,'sum8');a=pack(b'AB',m);q=pack(b'CDEF',m);obs=q[:4]+b'\x90'+q[4:];b=pack(b'GH',m)
        row=repair_stream(a+obs+b,m,{4:Profile(4,((0,255),),20,20)})[0]
        self.assertEqual(row['status'],'profile_conflict');self.assertIsNone(row['proposed_hex'])
    def test_edge_and_multi_edit_outside(self):
        m=FrameModel(b'\xb8\x34',2,1,'little',3,1,'sum8');q=pack(b'ABCDEF',m);a=pack(b'AB',m)
        self.assertEqual(repair_stream(q[:4]+q[5:]+a,m),[])
        self.assertEqual(candidates(q[:4]+q[6:],m)[0],'outside_edit_budget')
    def test_checksum_flip_competes_with_payload_flip(self):
        m=FrameModel(b'\xb8\x34',2,1,'little',3,1,'xor8');q=pack(b'ABCD',m);a=pack(b'XX',m);b=pack(b'YY',m)
        obs=q[:-1]+bytes([q[-1]^8]);row=repair_stream(a+obs+b,m)[0]
        self.assertEqual(row['trailer_flip_candidate_hex'],q.hex());self.assertIn(q.hex(),row['expanded_candidates_hex']);self.assertIsNone(row['proposed_hex']);self.assertEqual(row['status'],'ambiguous')
    def test_two_byte_length(self):
        m=FrameModel(b'\xb8\x34',2,2,'big',4,1,'crc8_smbus');p=bytes(range(256))*2;b=m.sync+len(p).to_bytes(2,'big')+p;q=b+bytes([checksum(b,m.checksum)])
        obs=q[:200]+q[201:];self.assertIn(q,candidates(obs,m)[1])
    def test_pipeline_opt_in(self):
        from protocol_zero.synthetic import make_capture
        a=[make_capture(991,80).data];b=[make_capture(992,80).data];c=[make_capture(993,80,noise='combined').data]
        base=analyze(a,b,c);new=analyze(a,b,c,repair=True)
        self.assertEqual(base['status'],'accepted');self.assertEqual(base['decoded'],new['decoded']);self.assertEqual(base['fields'],new['fields']);self.assertIn('repair_hypotheses',new)
if __name__=='__main__':unittest.main()
