import unittest
from robust import infer,graph
class Robust(unittest.TestCase):
 def test_noise(self):
  rows=[bytes((x,(7*x+31)%256 if x%10 else 0)) for x in range(80)]
  self.assertTrue(any(z[:5]==(0,1,'affine',7,31) for z in infer(rows[:40],rows[40:])))
 def test_constant(self):
  self.assertEqual(infer([b'aa']*20,[b'aa']*20),[])
 def test_graph(self):
  self.assertEqual(len(graph([(0,1,'xor',0,1,1,1),(0,1,'affine',1,1,1,1)])[(0,1)]),2)
