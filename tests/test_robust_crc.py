import random
import unittest
from collections import Counter
from protocol_zero.crc_discovery import CRCModel
from protocol_zero.joint_crc import _fit_exact, decode
from protocol_zero.robust_crc import ConsensusSolver, infer
from test_joint_crc import capture, M


def words(sizes, corrupt=()):
    r=random.Random(187)
    return {(b, M.predict(b) ^ (1 if i in corrupt else 0))
            for i,n in enumerate(sizes) for b in [r.randbytes(n)]}


def flatten(groups):
    return {m for g in groups for m in g}


class RobustTests(unittest.TestCase):
    def test_exact_equivalent(self):
        data=words(range(8,20))
        self.assertEqual(flatten(ConsensusSolver()(data,1)),flatten(_fit_exact(data)))

    def test_sparse_corruption(self):
        data=words(range(8,28),[2,6,10,14])
        self.assertFalse(_fit_exact(data))
        self.assertIn(M,flatten(ConsensusSolver()(data,.65)))

    def test_corrupted_anchor(self):
        data=words([8]*5+list(range(9,24)),[0,1,2,3])
        self.assertIn(M,flatten(ConsensusSolver()(data,.65)))

    def test_exact_consensus_for_one_polynomial(self):
        data=words([8,8,8,9,11,12,14,16], [1,3])
        actual={m for m in flatten(ConsensusSolver()(data,.65)) if m.poly==M.poly}
        expected=set()
        for init in range(256):
            votes=Counter(CRCModel(M.poly,init,0).predict(b)^c for b,c in data)
            expected.update(CRCModel(M.poly,init,xor) for xor,count in votes.items() if count>=6)
        self.assertEqual(actual,expected)

    def test_budget_never_returns_partial_models(self):
        a,_=capture(101,36); b,_=capture(202,24)
        r=infer([a],[b],max_votes=1)
        self.assertEqual(r['status'],'budget_exceeded'); self.assertFalse(r['models'])

    def test_end_to_end(self):
        a,_=capture(101,36,noise=True);b,_=capture(202,24,noise=True);c,t=capture(303,30,noise=True)
        r=infer([a],[b]);self.assertTrue(r['search']['complete'])
        self.assertTrue(any(M in ms for _,ms in r['models']))
        self.assertEqual(decode(c,r['models'])['agreed'],t)

    def test_independent_rejection(self):
        a,_=capture(101,36,outside=True);b,_=capture(202,24,outside=True)
        self.assertEqual(infer([a],[b])['status'],'rejected')

if __name__=='__main__':unittest.main()
