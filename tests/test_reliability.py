import random
import unittest

from protocol_zero.reliability import (
    EvidenceObservation,
    ReliabilityProfile,
    assess_pairwise_dependence,
    calibrate_sources,
    evaluate_hypothesis,
    observations_from_audit,
    wilson_interval,
)


def profile(source, group, *, tp=96, fn=4, tn=97, fp=3, calibration="cal-v1", minimum=30):
    return ReliabilityProfile(source, group, calibration, "bench-hw-v1", tp, fp, tn, fn, minimum)


class WilsonTests(unittest.TestCase):
    def test_interval_contains_observed_rate(self):
        lo, hi = wilson_interval(90, 100)
        self.assertLess(lo, 0.9)
        self.assertGreater(hi, 0.9)

    def test_invalid_counts_rejected(self):
        for args in ((-1, 10), (11, 10), (0, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                wilson_interval(*args)


class DependenceCalibrationTests(unittest.TestCase):
    def test_calibration_builder_recovers_source_profiles(self):
        labels = [True, True, False, False]
        predictions = {"a": [True, False, False, True],
                       "b": [True, False, False, True]}
        profiles, pairs = calibrate_sources(
            labels, predictions, {"a": "g-a", "b": "g-b"},
            calibration_set_id="cal", environment_id="env", min_per_class=2)
        self.assertEqual((profiles[0].true_positive, profiles[0].false_negative), (1, 1))
        self.assertEqual((profiles[0].true_negative, profiles[0].false_positive), (1, 1))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].status, "uncertain")

    def test_common_mode_errors_are_detected(self):
        labels = [True] * 100 + [False] * 100
        predictions = {"a": [], "b": []}
        for truth in labels:
            output = truth if len(predictions["a"]) % 10 != 0 else not truth
            predictions["a"].append(output)
            predictions["b"].append(output)
        assessment = assess_pairwise_dependence(
            labels, predictions, "a", "b", calibration_set_id="cal",
            environment_id="env", min_per_class=30)
        self.assertEqual(assessment.status, "dependent")
        self.assertGreater(assessment.positive_error_phi, 0.99)
        self.assertGreater(assessment.negative_error_phi, 0.99)

    def test_independent_error_patterns_are_not_flagged_as_large(self):
        rng = random.Random(1234)
        labels = [True] * 1000 + [False] * 1000
        predictions = {"a": [], "b": []}
        for truth in labels:
            for source, rate in (("a", 0.9), ("b", 0.9)):
                support = rng.random() < (rate if truth else 1.0 - rate)
                predictions[source].append(support)
        assessment = assess_pairwise_dependence(
            labels, predictions, "a", "b", calibration_set_id="cal",
            environment_id="env", min_per_class=100)
        self.assertEqual(assessment.status, "no_large_correlation_detected")

    def test_insufficient_pairwise_samples_are_uncertain(self):
        labels = [True] * 10 + [False] * 10
        predictions = {"a": [True] * 20, "b": [True] * 20}
        assessment = assess_pairwise_dependence(
            labels, predictions, "a", "b", calibration_set_id="cal",
            environment_id="env", min_per_class=30)
        self.assertEqual(assessment.status, "uncertain")

    def test_calibration_builder_rejects_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            calibrate_sources([True, False], {"a": [True]}, {"a": "g"},
                              calibration_set_id="cal", environment_id="env")


class ReliabilityFusionTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [profile("uart", "capture-uart"),
                         profile("schema", "specification"),
                         profile("timing", "timer-hardware")]

    def test_strong_independent_support_accepts(self):
        result = evaluate_hypothesis(
            [EvidenceObservation("uart", True), EvidenceObservation("schema", True),
             EvidenceObservation("timing", True)], self.profiles,
            evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1",
            require_dependence_audit=False)
        self.assertEqual(result["decision"], "support")
        self.assertGreaterEqual(result["posterior_envelope"][0], 0.95)
        self.assertFalse(result["integrity_verified"])

    def test_strong_independent_negative_evidence_rejects(self):
        result = evaluate_hypothesis(
            [EvidenceObservation("uart", False), EvidenceObservation("schema", False),
             EvidenceObservation("timing", False)], self.profiles,
            evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1",
            require_dependence_audit=False)
        self.assertEqual(result["decision"], "reject")
        self.assertLessEqual(result["posterior_envelope"][1], 0.05)

    def test_one_group_cannot_decide(self):
        result = evaluate_hypothesis([EvidenceObservation("uart", True)], self.profiles,
                                     evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["reason"], "insufficient_distinct_calibrated_provenance_groups")

    def test_correlated_sources_cannot_be_counted_twice(self):
        profiles = [profile("uart-a", "same-capture"), profile("uart-b", "same-capture")]
        with self.assertRaisesRegex(ValueError, "share independence group"):
            evaluate_hypothesis([EvidenceObservation("uart-a", True),
                                 EvidenceObservation("uart-b", True)], profiles,
                                evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")

    def test_calibration_evaluation_leakage_rejected(self):
        with self.assertRaisesRegex(ValueError, "data leakage"):
            evaluate_hypothesis([EvidenceObservation("uart", True),
                                 EvidenceObservation("schema", True)], self.profiles,
                                evaluation_set_id="cal-v1", evaluation_environment_id="bench-hw-v1")

    def test_insufficient_calibration_is_skipped_and_causes_abstention(self):
        weak = profile("weak", "weak-source", tp=8, fn=2, tn=8, fp=2, minimum=30)
        result = evaluate_hypothesis([EvidenceObservation("weak", True)], [weak],
                                     evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["skipped_evidence"][0]["reason"], "insufficient_calibration")

    def test_near_random_sources_produce_abstention(self):
        weak_profiles = [profile("a", "a", tp=55, fn=45, tn=53, fp=47),
                         profile("b", "b", tp=52, fn=48, tn=54, fp=46)]
        result = evaluate_hypothesis([EvidenceObservation("a", True),
                                      EvidenceObservation("b", True)], weak_profiles,
                                     evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1",
            require_dependence_audit=False)
        self.assertEqual(result["decision"], "abstain")

    def test_environment_mismatch_skips_stale_calibration(self):
        result = evaluate_hypothesis(
            [EvidenceObservation("uart", True), EvidenceObservation("schema", True)],
            self.profiles, evaluation_set_id="holdout-v1",
            evaluation_environment_id="bench-hw-v2")
        self.assertEqual(result["decision"], "abstain")
        self.assertTrue(all(x["reason"] == "environment_mismatch" for x in result["skipped_evidence"]))

    def test_unavailable_observation_is_not_negative_evidence(self):
        result = evaluate_hypothesis([EvidenceObservation("uart", True),
                                      EvidenceObservation("schema", None)], self.profiles,
                                     evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["skipped_evidence"][0]["reason"], "observation_unavailable")

    def test_missing_profile_is_not_silently_trusted(self):
        result = evaluate_hypothesis([EvidenceObservation("unknown", True)], [],
                                     evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["skipped_evidence"][0]["reason"], "missing_calibration_profile")

    def test_duplicate_source_observation_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate observation"):
            evaluate_hypothesis([EvidenceObservation("uart", True),
                                 EvidenceObservation("uart", False)], self.profiles,
                                evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")

    def test_invalid_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_hypothesis([], [], evaluation_set_id="holdout", evaluation_environment_id="bench-hw-v1", accept_threshold=0.5)
        with self.assertRaises(ValueError):
            evaluate_hypothesis([], [], evaluation_set_id="holdout", evaluation_environment_id="bench-hw-v1", reject_threshold=0.5)

    def test_prior_changes_posterior_envelope(self):
        observations = [EvidenceObservation("uart", True), EvidenceObservation("schema", True)]
        neutral = evaluate_hypothesis(observations, self.profiles,
                                      evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1", prior_probability=0.5, require_dependence_audit=False)
        skeptical = evaluate_hypothesis(observations, self.profiles,
                                        evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1", prior_probability=0.1, require_dependence_audit=False)
        self.assertLess(skeptical["posterior_envelope"][0], neutral["posterior_envelope"][0])

    def test_audit_adapter_collapses_multiple_rules_per_source(self):
        rows = observations_from_audit({"evidence": [
            {"source_id": "spec", "status": "supported"},
            {"source_id": "spec", "status": "supported"},
            {"source_id": "uart", "status": "contradicted"},
        ]})
        self.assertEqual(rows, [EvidenceObservation("spec", True),
                                EvidenceObservation("uart", False)])

    def test_audit_adapter_does_not_turn_mixed_source_evidence_into_negative(self):
        rows = observations_from_audit({"evidence": [
            {"source_id": "spec", "status": "supported"},
            {"source_id": "spec", "status": "contradicted"},
            {"source_id": "timing", "status": "unknown"},
        ]})
        self.assertEqual(rows, [EvidenceObservation("spec", None),
                                EvidenceObservation("timing", None)])

    def test_bonferroni_adjustment_grows_with_source_count(self):
        two = evaluate_hypothesis([EvidenceObservation("uart", True),
                                   EvidenceObservation("schema", True)], self.profiles,
                                  evaluation_set_id="holdout-v1",
                                  evaluation_environment_id="bench-hw-v1", require_dependence_audit=False)
        three = evaluate_hypothesis([EvidenceObservation("uart", True),
                                     EvidenceObservation("schema", True),
                                     EvidenceObservation("timing", True)], self.profiles,
                                    evaluation_set_id="holdout-v1",
                                    evaluation_environment_id="bench-hw-v1", require_dependence_audit=False)
        self.assertGreater(three["bonferroni_wilson_z"], two["bonferroni_wilson_z"])

    def test_dependence_audit_blocks_correlated_sources(self):
        labels = [True] * 100 + [False] * 100
        predictions = {"uart": [], "schema": []}
        for i, truth in enumerate(labels):
            output = truth if i % 10 != 0 else not truth
            predictions["uart"].append(output)
            predictions["schema"].append(output)
        profiles, dependence = calibrate_sources(
            labels, predictions, {"uart": "group-a", "schema": "group-b"},
            calibration_set_id="cal-v1", environment_id="bench-hw-v1", min_per_class=30)
        result = evaluate_hypothesis(
            [EvidenceObservation("uart", True), EvidenceObservation("schema", True)], profiles,
            evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1",
            dependence_assessments=dependence, require_dependence_audit=True)
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["reason"], "calibration_detected_correlated_errors")

    def test_required_but_missing_dependence_audit_abstains(self):
        result = evaluate_hypothesis(
            [EvidenceObservation("uart", True), EvidenceObservation("schema", True)], self.profiles,
            evaluation_set_id="holdout-v1", evaluation_environment_id="bench-hw-v1")
        self.assertEqual(result["decision"], "abstain")
        self.assertEqual(result["reason"], "dependence_audit_missing")

    def test_bool_not_accepted_as_integer_calibration_count(self):
        with self.assertRaises(ValueError):
            ReliabilityProfile("x", "g", "cal", "env", True, 1, 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
