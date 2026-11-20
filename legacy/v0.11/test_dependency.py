import unittest
from dependency import infer
class Tests(unittest.TestCase):
 def test_carry(self):
  r=infer([i.to_bytes(2,'little') for i in range(250,270)]); self.assertEqual(r[0]['width'],2); self.assertEqual(r[0]['score'],1); self.assertEqual(len(r),2)
 def test_no_carry(self):
  r=infer([i.to_bytes(2,'little') for i in range(10,20)]); self.assertEqual(r[0]['score'],0); self.assertEqual(len(r),2)
 def test_double(self):
  r=infer([i.to_bytes(4,'little') for i in range(65530,65550)]); self.assertEqual(r[0]['width'],4); self.assertEqual(r[0]['score'],2)
 def test_step(self): self.assertEqual(infer([bytes([i]) for i in range(0,30,3)]),[])
if __name__=='__main__':unittest.main()
