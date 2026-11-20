import unittest
from ambiguity import hypotheses,update
class Test(unittest.TestCase):
 def test_prefix(self):
  x=[i.to_bytes(2,'little') for i in range(20)]
  self.assertEqual(hypotheses(x),[(1,'little'),(2,'little')])
 def test_wrap(self):
  self.assertEqual(update([(1,'little'),(2,'little')],b'\xff\x00',b'\x00\x01'),[(1,'little'),(2,'little')])
 def test_reject(self):
  self.assertEqual(hypotheses([b'\x01',b'\x03']),[])
if __name__=='__main__':unittest.main()
