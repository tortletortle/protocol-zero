import unittest
from cadence import diagnose,infer
from evaluate_v16 import samples
class Cadence(unittest.TestCase):
    def test_non_power_of_two(self):
        p,q,_=samples(16000,'signal',3)
        self.assertEqual(diagnose(p)['block_size'],3)
        self.assertEqual(infer(p,q)['status'],'ok')
    def test_constant(self):
        self.assertEqual(diagnose([b'aa']*100)['status'],'insufficient_changes')
    def test_mismatch(self):
        p,q,_=samples(16000,'signal',8)
        q[1]=b'zz'
        self.assertEqual(infer(p,q)['status'],'cadence_mismatch')
    def test_cycle(self):
        p,q,_=samples(16000,'cycle')
        self.assertEqual(infer(p,q)['status'],'unresolved_dependence')
    def test_signal(self):
        p,q,(a,b)=samples(16000,'signal',8)
        self.assertTrue(any((z['kind'],z['a'],z['b'])==('affine',a,b) for z in infer(p,q)['edges']))
    def test_ragged(self):
        self.assertEqual(diagnose([b'a',b'ab']*20)['status'],'insufficient_or_ragged')
