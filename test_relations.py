import unittest, random
from relations import infer,counters
class Relations(unittest.TestCase):
 def test_affine(self):
  r=[bytes((x,(7*x+31)%256)) for x in range(40)]; self.assertIn((0,1,'affine',7,31),infer(r[:20],r[20:]))
 def test_xor(self):
  r=[bytes((x,x^93)) for x in range(40)]; self.assertIn((0,1,'xor',93),infer(r[:20],r[20:]))
 def test_shift(self):
  r=[b'\xff'+((65500+3*x)%65536).to_bytes(2,'little') for x in range(40)]; self.assertIn((1,2,'little',3),counters(r[:20],r[20:]))
 def test_reject(self):
  r=[bytes((x,x)) for x in range(20)]+[bytes((x,x^77)) for x in range(20,40)]; self.assertNotIn((0,1,'affine',1,0),infer(r[:20],r[20:]))
