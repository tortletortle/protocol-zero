import random
import unittest
from protocol_zero.joint_crc import Layout, infer, decode, MAX_BYTES, _fit_exact
from protocol_zero.crc_discovery import CRCModel, fit_train
from protocol_zero.checksums import crc8

SYNC=b'\xd5\x7e'
M=CRCModel(0x9b,84,18)


def capture(seed, count, *, wide=False, suffix=0, start=0, noise=False, outside=False, fixed=False):
    r=random.Random(seed); out=bytearray(r.randbytes(5)); truth=[]
    for i in range(count):
        n=12 if fixed else (15,28,270)[i%3] if wide else (8,13,22)[i%3]
        p=r.randbytes(n)
        body=SYNC+bytes([i%256])+n.to_bytes(2 if wide else 1,'big')+p
        c=(sum(x*x for x in body[start:])+17)%256 if outside else crc8(body[start:],M.poly,M.init,M.xorout)
        q=body+bytes([c])+r.randbytes(suffix)
        good=not noise or i%11!=3
        if not good:
            j=len(q)-suffix-2; q=q[:j]+bytes([q[j]^1])+q[j+1:]
        a=len(out);out.extend(q)
        if good:truth.append((a,len(out)))
        out.extend(r.randbytes(i%3))
    return bytes(out),truth


class JointTests(unittest.TestCase):
    def run_case(self, **kw):
        a,_=capture(101,36,**kw); b,_=capture(202,24,**kw); c,t=capture(303,30,**kw)
        f=infer([a],[b]); self.assertTrue(f['models'])
        expected=Layout(SYNC,3,2 if kw.get('wide') else 1,'big' if kw.get('wide') else 'little',5 if kw.get('wide') else 4,kw.get('suffix',0),kw.get('start',0))
        self.assertTrue(any(l==expected and M in ms for l,ms in f['models']))
        d=decode(c,f['models'])
        if kw.get('suffix'):
            self.assertEqual(d['agreed'],[])
            self.assertTrue(set(t)<={(a,b) for a,b,_ in d['contested']})
            self.assertEqual({l.suffix for l,_ in f['models']},{0,1})
        else:
            self.assertEqual(d['agreed'],t)
        return f

    def test_raw_unknown_crc(self): self.run_case()
    def test_wide_and_suffix(self): self.run_case(wide=True,suffix=1,start=2)
    def test_noisy(self): self.run_case(noise=True)
    def test_constant_sync_coverage_ambiguity(self):
        f=self.run_case()
        self.assertEqual({l.coverage_start for l,_ in f['models']},{0,2})
        self.assertEqual(f['status'],'ambiguous')
    def test_outside_family(self):
        a,_=capture(101,36,outside=True);b,_=capture(202,24,outside=True)
        self.assertEqual(infer([a],[b])['status'],'rejected')
    def test_duplicate_validation_is_not_independent(self):
        a,_=capture(101,36)
        self.assertEqual(infer([a],[a])['status'],'rejected')
    def test_budget_and_empty(self):
        self.assertEqual(infer([],[])['status'],'insufficient_data')
        self.assertEqual(infer([bytes(MAX_BYTES)],[b'x'])['status'],'budget_exceeded')
        self.assertEqual(decode(b'abc',[])['agreed'],[])
    def test_no_repeat_length_exact_solver(self):
        r=random.Random(777); words=set()
        for n in range(8,24):
            b=r.randbytes(n);words.add((b,M.predict(b)))
        answers=[m for group in _fit_exact(words) for m in group]
        self.assertIn(M,answers)
        self.assertTrue(all(all(m.predict(b)==c for b,c in words) for m in answers))
    def test_exact_agrees_with_prior_parameter_search(self):
        for seed in range(916,920):
            r=random.Random(seed);m=CRCModel(r.randrange(1,256,2),r.randrange(256),r.randrange(256))
            data={b:m.predict(b) for b in (r.randbytes(n) for n in (5,7,9,12,15,22))}
            self.assertEqual({x for g in _fit_exact(set(data.items())) for x in g},set(fit_train(data)))
    def test_fixed_length_retains_behaviors(self):
        a,_=capture(101,36,fixed=True);b,_=capture(202,24,fixed=True);c,t=capture(303,30,fixed=True)
        f=infer([a],[b]);self.assertEqual(f['status'],'ambiguous')
        self.assertTrue(any(M in ms for _,ms in f['models']))
        self.assertEqual(decode(c,f['models'])['agreed'],t)

if __name__=='__main__':unittest.main()
