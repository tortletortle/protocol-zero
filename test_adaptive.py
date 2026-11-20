import unittest,random
from adaptive import infer
class Adaptive(unittest.TestCase):
 def test_signal(self):
  r=[bytes((x,(7*x+31)%256 if x%3 else 0)) for x in range(120)]
  self.assertTrue(any(z[:5]==(0,1,'affine',7,31) for z in infer(r[:60],r[60:],permutations=199)))
 def test_constant(self):
  self.assertEqual(infer([b'aa']*32,[b'aa']*32),[])
 def test_resolution(self):
  r=[bytes((x,x,x)) for x in range(64)]
  self.assertEqual(infer(r[:32],r[32:],permutations=19),[])
