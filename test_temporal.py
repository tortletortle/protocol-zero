import unittest
from temporal import infer
from evaluate_v15 import samples
class Temporal(unittest.TestCase):
    def test_signal(self):
        p,q,(a,b)=samples(15002,'affine_burst')
        self.assertTrue(any((z['kind'],z['a'],z['b'])==('affine',a,b) for z in infer(p,q,8,permutations=199)['edges']))
    def test_partial_block(self):
        with self.assertRaises(ValueError): infer([b'ab']*32,[b'ab']*31,8)
    def test_few_blocks(self):
        self.assertEqual(infer([b'ab']*32,[b'ab']*32,8)['status'],'insufficient_blocks')
    def test_resolution(self):
        r=[bytes((x,x,x)) for x in range(32)]
        self.assertEqual(infer(r,r,1,permutations=19)['status'],'insufficient_permutations')
