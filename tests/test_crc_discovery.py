import random
import unittest
from protocol_zero.checksums import crc8
from protocol_zero.crc_discovery import CRCModel, discover, fit_train, groups, plan, refine, samples


def words(m, sizes, seed):
    r = random.Random(seed)
    out = []
    for n in sizes:
        b = r.randbytes(n)
        out.append(b + bytes([crc8(b,m.poly,m.init,m.xorout)]))
    return out


class CRCTests(unittest.TestCase):
    def test_catalogue(self):
        self.assertEqual([CRCModel(*x).predict(b'123456789') for x in [(7,0,0),(29,255,255),(47,255,255)]], [0xf4,0x4b,0xdf])

    def test_independent_crc(self):
        m = CRCModel(0x9B,123,45)
        r = discover(words(m,[5,5,6,6,7,7,8,8],1),words(m,[5,6,7,8,9,9],2))
        self.assertIn(m,r['models'])
        self.assertEqual(len(groups(r['models'])),1)
        self.assertEqual(r['presets'],[])

    def test_fixed_length_and_active_resolution(self):
        m = CRCModel(0x1D,44,76)
        r = discover(words(m,[8]*10,1),words(m,[8]*6,2))
        self.assertEqual(len(r['models']),256)
        self.assertEqual(r['status'],'ambiguous')
        p = plan(r['models'],[bytes(n) for n in [8,9,10]])
        self.assertEqual(p[0]['body_hex'],bytes(9).hex())
        b = bytes.fromhex(p[0]['body_hex'])
        self.assertEqual(len(groups(refine(r['models'],[b+bytes([m.predict(b)])]))),1)
        self.assertEqual(refine(r['models'],[]),r['models'])

    def test_global_equivalence(self):
        m=CRCModel(7,0,0)
        equiv=[CRCModel(7,i,i) for i in range(256) if CRCModel(7,i,i).behavior_key()==m.behavior_key()]
        self.assertGreater(len(equiv),1)
        self.assertEqual(len(groups(equiv)),1)
        self.assertEqual(plan(equiv,[bytes(n) for n in range(1,20)]),[])
        for b in [b'a', b'123456789', bytes(range(200))]:
            self.assertEqual(len({x.predict(b) for x in equiv}),1)

    def test_holdout_nonoverlap(self):
        m=CRCModel(29,0,0);a=words(m,[8]*10,1)
        self.assertEqual(discover(a,a)['status'],'insufficient_data')

    def test_conflict_and_bounds(self):
        with self.assertRaises(ValueError): samples([b'ab\x00',b'ab\x01'])
        with self.assertRaises(ValueError): samples([b''])
        with self.assertRaises(ValueError): CRCModel(2,0,0)

    def test_outside_family(self):
        rng=random.Random(11)
        a=[b+bytes([(sum(x*x for x in b)+17)%256]) for b in [rng.randbytes(9) for _ in range(16)]]
        self.assertEqual(discover(a[:10],a[10:])['status'],'rejected')

    def test_train_solver_exhaustive_subset(self):
        m=CRCModel(29,37,61);a=samples(words(m,[4,4,5,5],7))
        found={x for x in fit_train(a) if x.poly==29}
        b,c=next(iter(a.items()))
        oracle=set()
        for i in range(256):
            x=crc8(b,29,i)^c
            if all(crc8(q,29,i,x)==v for q,v in a.items()):oracle.add(CRCModel(29,i,x))
        self.assertEqual(found,oracle)

if __name__=='__main__': unittest.main()
