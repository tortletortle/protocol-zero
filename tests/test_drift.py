import random, unittest
from dataclasses import dataclass
from protocol_zero.drift import (LikelihoodCUSUM,PageHinkleyIncrease,
    HoeffdingWindowDetector,MonitorConfig,monitor_source)

@dataclass
class Profile:
    source_id:str="boundary-a"
    calibration_set_id:str="cal-v1"
    environment_id:str="bench-v1"
    positive_examples:int=500
    negative_examples:int=500
    false_negative:int=25
    false_positive:int=25
    calibrated:bool=True

def feedback(errors,truth=True):
    return [(truth,not e if truth else e) for e in errors]

class DriftTests(unittest.TestCase):
    def test_cusum_detects_step_increase(self):
        d=LikelihoodCUSUM(.05,.15,9); rng=random.Random(17)
        for i in range(2500):
            p=.05 if i<600 else .20
            d.update(rng.random()<p,i)
            if d.alarm_at is not None: break
        self.assertIsNotNone(d.alarm_at); self.assertGreaterEqual(d.alarm_at,600); self.assertLess(d.alarm_at,800)

    def test_page_hinkley_detects_step_increase(self):
        d=PageHinkleyIncrease(.05,.02,10); rng=random.Random(18)
        for i in range(2500):
            p=.05 if i<600 else .20
            d.update(rng.random()<p,i)
            if d.alarm_at is not None: break
        self.assertIsNotNone(d.alarm_at); self.assertLess(d.alarm_at,850)

    def test_window_detects_step_increase(self):
        d=HoeffdingWindowDetector(64,2048,.01,16); rng=random.Random(19)
        for i in range(2500):
            p=.05 if i<600 else .20
            d.update(rng.random()<p,i)
            if d.alarm_at is not None: break
        self.assertIsNotNone(d.alarm_at); self.assertGreaterEqual(d.alarm_at,600)

    def test_monitor_uses_two_of_three_alert(self):
        rng=random.Random(20); errors=[rng.random()<(.05 if i<600 else .20) for i in range(2500)]
        p=Profile(); before=(p.false_negative,p.false_positive)
        r=monitor_source(p,feedback(errors),evaluation_set_id="holdout-v1",evaluation_environment_id="bench-v1")
        self.assertEqual(r["status"],"drift_alert")
        self.assertEqual(r["classes"]["valid_candidates"]["status"],"drift_alert")
        self.assertEqual(before,(p.false_negative,p.false_positive))
        self.assertFalse(r["calibration_updated"]); self.assertFalse(r["integrity_verified"])

    def test_environment_mismatch_abstains(self):
        r=monitor_source(Profile(),feedback([False]*100),evaluation_set_id="holdout",evaluation_environment_id="bench-v2")
        self.assertEqual(r["status"],"abstain"); self.assertEqual(r["reason"],"environment_mismatch")

    def test_same_calibration_and_evaluation_id_rejected(self):
        with self.assertRaisesRegex(ValueError,"data leakage"):
            monitor_source(Profile(),feedback([False]*100),evaluation_set_id="cal-v1",evaluation_environment_id="bench-v1")

    def test_insufficient_class_feedback_is_not_negative(self):
        r=monitor_source(Profile(),feedback([False]*10),evaluation_set_id="holdout",evaluation_environment_id="bench-v1")
        self.assertEqual(r["status"],"abstain"); self.assertEqual(r["reason"],"insufficient_feedback")

    def test_false_positive_stream_monitored_separately(self):
        rng=random.Random(21); rows=[]
        for i in range(2500):
            fp=rng.random()<(.05 if i<600 else .20); rows.append((False,fp))
        r=monitor_source(Profile(),rows,evaluation_set_id="holdout",evaluation_environment_id="bench-v1")
        self.assertEqual(r["classes"]["invalid_candidates"]["status"],"drift_alert")
        self.assertEqual(r["classes"]["valid_candidates"]["status"],"insufficient_feedback")

    def test_improvement_does_not_trigger_increase_detectors(self):
        rng=random.Random(22); errors=[rng.random()<(.05 if i<600 else .01) for i in range(2500)]
        r=monitor_source(Profile(),feedback(errors),evaluation_set_id="holdout",evaluation_environment_id="bench-v1")
        self.assertNotEqual(r["status"],"drift_alert")

    def test_feedback_requires_boolean_labels(self):
        with self.assertRaises(ValueError):
            monitor_source(Profile(),[(1,True)],evaluation_set_id="holdout",evaluation_environment_id="bench-v1")

    def test_window_parameters_validated(self):
        with self.assertRaises(ValueError): HoeffdingWindowDetector(64,100)
        with self.assertRaises(ValueError): MonitorConfig(window_min=128,window_max=128)

    def test_high_baseline_skips_unavailable_cusum_safely(self):
        p=Profile(false_negative=480); r=monitor_source(p,[(True,True)]*100,
            evaluation_set_id="holdout",evaluation_environment_id="bench-v1")
        d=r["classes"]["valid_candidates"]
        self.assertEqual(d["detector_count"],2)
        self.assertFalse(d["detectors"]["likelihood_cusum"]["available"])
        self.assertIn("valid_candidates",r["monitored_classes"])

    def test_detector_rejects_non_boolean_error(self):
        with self.assertRaises(ValueError): LikelihoodCUSUM(.05).update(1,0)

if __name__=="__main__": unittest.main()
