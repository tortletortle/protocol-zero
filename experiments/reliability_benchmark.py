"""Deterministic synthetic benchmark for calibrated evidence abstention.

Calibration and evaluation samples use disjoint identifiers. The generator
contains independent-source, weak-source, known/hidden environment drift, and
common-mode error scenarios. Results are mechanism evidence, not real-protocol
performance claims.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol_zero.reliability import (
    EvidenceObservation,
    calibrate_sources,
    evaluate_hypothesis,
)

SEED = 20261123
CALIBRATION_N_PER_CLASS = 500
EVALUATION_N = 4000
MIN_PER_CLASS = 30
ENV_V1 = "bench-hw-v1"
ENV_V2 = "bench-hw-v2"
SOURCE_IDS = ["boundary-a", "schema-b", "timing-c"]
GROUPS = ["uart-hardware-a", "protocol-spec-b", "clock-hardware-c"]

SCENARIOS = {
    "nominal": {
        "calibration_rates": [(0.98, 0.98), (0.94, 0.96), (0.90, 0.93)],
        "evaluation_rates": [(0.98, 0.98), (0.94, 0.96), (0.90, 0.93)],
    },
    "one_near_random_source": {
        "calibration_rates": [(0.98, 0.98), (0.94, 0.96), (0.52, 0.51)],
        "evaluation_rates": [(0.98, 0.98), (0.94, 0.96), (0.52, 0.51)],
    },
    "two_moderate_one_weak": {
        "calibration_rates": [(0.90, 0.91), (0.87, 0.89), (0.53, 0.52)],
        "evaluation_rates": [(0.90, 0.91), (0.87, 0.89), (0.53, 0.52)],
    },
    "one_adversarial_but_calibrated": {
        "calibration_rates": [(0.98, 0.98), (0.94, 0.96), (0.12, 0.10)],
        "evaluation_rates": [(0.98, 0.98), (0.94, 0.96), (0.12, 0.10)],
    },
    "known_environment_mismatch": {
        "calibration_rates": [(0.98, 0.98), (0.94, 0.96), (0.90, 0.93)],
        "evaluation_rates": [(0.98, 0.98), (0.94, 0.96), (0.90, 0.93)],
        "evaluation_environment": ENV_V2,
    },
    "undetected_environment_drift": {
        "calibration_rates": [(0.98, 0.98), (0.94, 0.96), (0.90, 0.93)],
        "evaluation_rates": [(0.56, 0.55), (0.54, 0.53), (0.52, 0.51)],
    },
    "mislabeled_common_mode_errors": {
        "calibration_rates": [(0.99, 0.99), (0.99, 0.99), (0.99, 0.99)],
        "evaluation_rates": [(0.99, 0.99), (0.99, 0.99), (0.99, 0.99)],
        "common_mode_error_calibration": 0.10,
        "common_mode_error_evaluation": 0.10,
    },
}


def _make_predictions(rng, labels, rates, common_mode_error=0.0):
    outputs = {source: [] for source in SOURCE_IDS}
    for truth in labels:
        common_flip = rng.random() < common_mode_error
        for source, (sensitivity, specificity) in zip(SOURCE_IDS, rates):
            if common_flip:
                output = not truth
            else:
                pass_probability = sensitivity if truth else 1.0 - specificity
                output = rng.random() < pass_probability
            outputs[source].append(output)
    return outputs


def _metrics(rows, key):
    n = len(rows)
    positives = [x for x in rows if x["truth"]]
    negatives = [x for x in rows if not x["truth"]]
    predicted = [x for x in rows if x[key] is not None]
    decided_correct = [x for x in predicted if x[key] == x["truth"]]
    accepted = [x for x in rows if x[key] is True]
    rejected = [x for x in rows if x[key] is False]
    return {
        "n": n,
        "coverage": len(predicted) / n,
        "abstention_rate": 1.0 - len(predicted) / n,
        "accuracy_on_decided": len(decided_correct) / len(predicted) if predicted else None,
        "false_accept_rate_all_invalid": sum(x[key] is True for x in negatives) / len(negatives),
        "false_reject_rate_all_valid": sum(x[key] is False for x in positives) / len(positives),
        "false_accept_fraction_of_accepts": sum(not x["truth"] for x in accepted) / len(accepted) if accepted else None,
        "false_reject_fraction_of_rejects": sum(x["truth"] for x in rejected) / len(rejected) if rejected else None,
    }


def run_scenario(name, config, seed):
    rng = random.Random(seed)
    calibration_labels = ([True] * CALIBRATION_N_PER_CLASS
                          + [False] * CALIBRATION_N_PER_CLASS)
    calibration_predictions = _make_predictions(
        rng, calibration_labels, config["calibration_rates"],
        config.get("common_mode_error_calibration", 0.0))
    calibration_environment = config.get("calibration_environment", ENV_V1)
    evaluation_environment = config.get("evaluation_environment", ENV_V1)
    profiles, dependence = calibrate_sources(
        calibration_labels, calibration_predictions,
        dict(zip(SOURCE_IDS, GROUPS)),
        calibration_set_id=f"{name}-calibration-v1",
        environment_id=calibration_environment,
        min_per_class=MIN_PER_CLASS,
        correlation_threshold=0.25,
    )

    evaluation_labels = [i % 2 == 0 for i in range(EVALUATION_N)]
    evaluation_predictions = _make_predictions(
        rng, evaluation_labels, config["evaluation_rates"],
        config.get("common_mode_error_evaluation", 0.0))
    rows = []
    for i, truth in enumerate(evaluation_labels):
        verdicts = [evaluation_predictions[source][i] for source in SOURCE_IDS]
        majority = sum(verdicts) >= 2
        observations = [EvidenceObservation(source, verdict)
                        for source, verdict in zip(SOURCE_IDS, verdicts)]
        kwargs = dict(
            evaluation_set_id=f"{name}-holdout-v1",
            evaluation_environment_id=evaluation_environment,
            prior_probability=0.5,
            accept_threshold=0.95,
            reject_threshold=0.05,
            min_provenance_groups=2,
        )
        plain = evaluate_hypothesis(observations, profiles, require_dependence_audit=False, **kwargs)
        audited = evaluate_hypothesis(
            observations, profiles, dependence_assessments=dependence,
            require_dependence_audit=True, **kwargs)
        plain_prediction = (True if plain["decision"] == "support" else
                            False if plain["decision"] == "reject" else None)
        audited_prediction = (True if audited["decision"] == "support" else
                              False if audited["decision"] == "reject" else None)
        rows.append({"truth": truth, "majority": majority,
                     "calibrated": plain_prediction, "audited": audited_prediction})

    return {
        "scenario": name,
        "seed": seed,
        "calibration_n_per_class": CALIBRATION_N_PER_CLASS,
        "evaluation_n": EVALUATION_N,
        "calibration_environment_id": calibration_environment,
        "evaluation_environment_id": evaluation_environment,
        "common_mode_error_calibration": config.get("common_mode_error_calibration", 0.0),
        "common_mode_error_evaluation": config.get("common_mode_error_evaluation", 0.0),
        "observed_calibration_rates": [
            {"source_id": p.source_id, "group": p.independence_group,
             "positive_examples": p.positive_examples,
             "negative_examples": p.negative_examples,
             "sensitivity": p.true_positive / p.positive_examples if p.positive_examples else None,
             "specificity": p.true_negative / p.negative_examples if p.negative_examples else None}
            for p in profiles
        ],
        "pairwise_dependence_audit": [
            {"sources": [d.source_a, d.source_b],
             "positive_error_phi": d.positive_error_phi,
             "negative_error_phi": d.negative_error_phi,
             "status": d.status, "threshold": d.threshold}
            for d in dependence
        ],
        "metrics": {
            "majority_vote": _metrics(rows, "majority"),
            "calibrated_without_dependence_gate": _metrics(rows, "calibrated"),
            "calibrated_with_dependence_gate": _metrics(rows, "audited"),
        },
    }


def main():
    results = [run_scenario(name, config, SEED + i * 101)
               for i, (name, config) in enumerate(SCENARIOS.items())]

    def metric_summary(metrics):
        keys = ("coverage", "abstention_rate", "accuracy_on_decided",
                "false_accept_rate_all_invalid", "false_reject_rate_all_valid")
        return {key: metrics[key] for key in keys}

    scenarios = []
    for result in results:
        metrics = result["metrics"]
        scenarios.append({
            "scenario": result["scenario"],
            "seed": result["seed"],
            "calibration_environment_id": result["calibration_environment_id"],
            "evaluation_environment_id": result["evaluation_environment_id"],
            "majority_vote": metric_summary(metrics["majority_vote"]),
            "calibrated_without_dependence_gate": metric_summary(metrics["calibrated_without_dependence_gate"]),
            "calibrated_with_dependence_gate": metric_summary(metrics["calibrated_with_dependence_gate"]),
            "dependence_statuses": [
                {"sources": d["sources"], "positive_error_phi": d["positive_error_phi"],
                 "negative_error_phi": d["negative_error_phi"], "status": d["status"]}
                for d in result["pairwise_dependence_audit"]
            ],
        })
    payload = {
        "experiment": "V0.2.8 calibrated evidence fusion, dependence audit, and abstention",
        "seed_base": SEED,
        "calibration_n_per_class": CALIBRATION_N_PER_CLASS,
        "evaluation_n_per_scenario": EVALUATION_N,
        "scenarios": scenarios,
        "limitations": [
            "All captures and source verdicts are synthetic.",
            "Calibration and evaluation samples have separate IDs and random draws.",
            "The explicit environment mismatch is detectable only because the supplied environment IDs differ.",
            "Hidden drift under a reused environment ID is not detected by marginal calibration alone.",
            "The common-mode scenario deliberately gives correlated sources distinct provenance labels; pairwise error audit is expected to block fusion.",
            "Pairwise phi/Fisher-z checks are approximate and may miss nonlinear, conditional, or time-varying dependencies.",
            "No large correlation detected is not proof of statistical independence.",
            "Bonferroni adjustment covers marginal sensitivity/specificity Wilson intervals; posterior envelopes still rely on the likelihood model and prior.",
        ],
    }
    out = Path("experiments/v028_reliability_benchmark.json")
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
