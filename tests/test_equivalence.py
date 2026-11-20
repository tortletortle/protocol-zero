import random
import unittest
from protocol_zero.model import FrameModel
from protocol_zero.checksums import checksum
from protocol_zero.equivalence import fit_models, consensus, constraints, plan_lengths, refine, analyze_equivalence

SYNC=b'\xa6\x39'
NARROW=FrameModel(SYNC,2,1,'little',4,1,'crc8_smbus')
WIDE=FrameModel(SYNC,2,2,'little',4,1,'crc8_smbus')
BIG=FrameModel(SYNC,2,2,'big',4,1,'crc8_smbus')

def pack(m,n,seed):
    r=random.Random(seed)
    h=bytearray(m.payload_offset)
    h[:len(m.sync)]=m.sync
    h[m.length_offset:m.length_offset+m.length_width]=n.to_bytes(m.length_width,m.length_endian)
    body=bytes(h)+r.randbytes(n)
    return body+bytes([checksum(body,m.checksum)])

class EquivalenceTests(unittest.TestCase):
    def test_short_frames_equivalent(self):
        train=[b''.join(pack(WIDE,n,i) for i,n in enumerate([9,15,30]*15))]
        validation=[b''.join(pack(WIDE,n,i+200) for i,n in enumerate([9,15,30]*10))]
        fit=fit_models(train,validation)
        self.assertEqual(fit['status'],'observationally_equivalent')
        self.assertIn(WIDE,fit['models']);self.assertIn(NARROW,fit['models'])
        self.assertEqual(len(consensus(validation[0],fit['models'])['agreed']),30)

    def test_consensus_disagreement(self):
        raw=pack(WIDE,12,1)+pack(WIDE,300,2)
        report=consensus(raw,[WIDE,NARROW])
        self.assertEqual(len(report['agreed']),1)
        self.assertEqual(len(report['contested']),1)
        self.assertFalse(report['agreed'][0]['verified_ground_truth'])

    def test_one_sided_not_two_sided(self):
        self.assertEqual(plan_lengths([WIDE,NARROW],[20,120,260]),[])
        result=plan_lengths([WIDE,NARROW],[261,275])
        self.assertEqual(result[0]['total_size'],261)
        self.assertEqual(result[0]['one_sided'],[(0,1)])
        self.assertEqual(result[0]['two_sided'],[])

    def test_endian_two_sided(self):
        self.assertEqual(constraints(WIDE,261)[2],0)
        self.assertEqual(constraints(BIG,261)[2],1)
        p=plan_lengths([WIDE,BIG],[20,261])
        self.assertEqual(p[0]['two_sided'],[(0,1)])
        self.assertEqual(p[0]['feasible_models'],[0,1])

    def test_three_distinct_observations(self):
        a=pack(WIDE,300,1);b=pack(WIDE,300,2);c=pack(WIDE,300,3)
        self.assertEqual(refine([WIDE,NARROW],[a,a,a])['models'],[WIDE,NARROW])
        self.assertEqual(refine([WIDE,NARROW],[a,b])['status'],'insufficient_observations')
        result=refine([WIDE,NARROW],[a,b,c])
        self.assertEqual(result['models'],[WIDE]);self.assertEqual(result['status'],'unique_under_observations')

    def test_silence_is_not_evidence(self):
        self.assertEqual(refine([WIDE,NARROW],[])['models'],[WIDE,NARROW])

    def test_out_of_model(self):
        alien=FrameModel(b'\xb8\x34',2,1,'little',4,1,'crc8_smbus')
        result=refine([WIDE,NARROW],[pack(alien,20,i) for i in range(3)])
        self.assertEqual(result['status'],'all_conflicted');self.assertEqual(result['models'],[])

    def test_partial_conflict_does_not_claim_unique(self):
        frames=[pack(WIDE,300,i) for i in range(3)]
        bad=bytearray(pack(WIDE,300,9));bad[-1]^=1
        r=refine([WIDE,NARROW],frames+[bytes(bad)])
        self.assertEqual(r['models'],[WIDE]);self.assertEqual(r['status'],'narrowed')

    def test_no_models(self):
        r=analyze_equivalence([],[],[b'abc'],allowed_total_sizes=[260])
        self.assertEqual(r['status'],'insufficient_data')
        self.assertEqual(r['decoded'][0]['agreed'],[])
        self.assertEqual(r['acquisition_plan'],[])

    def test_all_candidates_retained_within_group(self):
        from unittest.mock import patch
        a={'records':[]}; scores=[(10,WIDE,a,a),(3,NARROW,a,a)]
        with patch('protocol_zero.equivalence.rank_hypotheses',return_value=scores):
            self.assertEqual(fit_models([b'a'],[b'b'])['models'],[WIDE,NARROW])

if __name__=='__main__':unittest.main()
