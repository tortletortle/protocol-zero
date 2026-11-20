import unittest,random
from session_model import fit,assess,choose,symbols
from evaluate_v21 import session,end_to_end

class SessionTests(unittest.TestCase):
    def test_context(self):
        p=['A','X','B']; q=['C','X','D']; z=['A','X','D']
        self.assertEqual(assess(fit([p,q],1),z)['status'],'consistent_with_model')
        self.assertEqual(assess(fit([p,q],2),z)['status'],'unseen_transition')
    def test_completion(self):
        self.assertEqual(assess(fit([['A','B']]),['A'])['event'],'@end')
    def test_selection(self):
        p=[['A','X','B'],['C','X','D']]; q=[['A','X','D']]
        self.assertEqual(choose(p,p,q)[1]['depth'],2)
        self.assertEqual(choose(p,p)[1]['depth'],1)
    def test_reserved(self):
        with self.assertRaises(ValueError): fit([['@end']])
    def test_unresolved(self):
        self.assertEqual(symbols({'groups':[]},[('C',b'abc')],0)['status'],'unresolved_framing')
    def test_integration(self):
        r=end_to_end(); self.assertTrue(r['exact_symbols']); self.assertEqual(r['positive_accept'],20); self.assertEqual(r['negative_flag'],20)
