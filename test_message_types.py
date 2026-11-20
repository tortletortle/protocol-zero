import random,unittest
from message_types import infer,events
from evaluate_v22 import sample

class MessageTypes(unittest.TestCase):
    def data(self,kind):
        r=random.Random(23000)
        return [sample(r,kind,4) for _ in range(24)],[sample(r,kind,5) for _ in range(12)]
    def test_type(self):
        self.assertEqual([x['offset'] for x in infer(*self.data('clean'))],[2])
    def test_alias(self):
        self.assertEqual({x['offset'] for x in infer(*self.data('alias'))},{2,4})
    def test_null(self): self.assertEqual(infer(*self.data('null')),[])
    def test_empty(self): self.assertEqual(infer([],[]),[])
    def test_direction(self): self.assertEqual(events([('C',b'\x10'),('S',b'\x10')],0),['C:10','S:10'])
