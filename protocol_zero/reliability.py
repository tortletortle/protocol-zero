"""Calibrated evidence fusion with provenance and dependence-aware abstention.

Sources are calibrated on a labelled dataset identified separately from the
evaluation dataset. At evaluation time, at most one observation per declared
provenance group is allowed. Optional pairwise error-correlation audits can
block multiplication of likelihood ratios when calibration errors co-move.

Distinct provenance groups and a low observed error correlation are not proof
of statistical independence. All outputs remain hypotheses, never integrity
proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atanh, exp, isfinite, log, sqrt, tanh
from statistics import NormalDist
from typing import Mapping, Sequence

_EPS = 1e-12


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _count(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _probability(value: float, name: str, *, open_interval: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if open_interval:
        if not 0.0 < value < 1.0:
            raise ValueError(f"{name} must be strictly between 0 and 1")
    elif not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Two-sided Wilson score interval for a binomial proportion."""
    _count(successes, "successes")
    _count(trials, "trials", 1)
    if successes > trials:
        raise ValueError("successes cannot exceed trials")
    if isinstance(z, bool) or not isinstance(z, (int, float)) or not isfinite(z) or z <= 0:
        raise ValueError("z must be a positive finite number")
    p = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = (p + z2 / (2.0 * trials)) / denom
    radius = (z * sqrt(p * (1.0 - p) / trials + z2 / (4.0 * trials * trials))) / denom
    return max(0.0, center - radius), min(1.0, center + radius)


@dataclass(frozen=True)
class ReliabilityProfile:
    """Confusion counts for one source on a labelled calibration dataset.

    Positive means the evaluated frame candidate is genuinely valid. The
    source's positive output means it supports that candidate.
    """
    source_id: str
    independence_group: str
    calibration_set_id: str
    environment_id: str
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    min_per_class: int = 30

    def __post_init__(self) -> None:
        _nonempty(self.source_id, "source_id")
        _nonempty(self.independence_group, "independence_group")
        _nonempty(self.calibration_set_id, "calibration_set_id")
        _nonempty(self.environment_id, "environment_id")
        for name in ("true_positive", "false_positive", "true_negative", "false_negative"):
            _count(getattr(self, name), name)
        _count(self.min_per_class, "min_per_class", 1)

    @property
    def positive_examples(self) -> int:
        return self.true_positive + self.false_negative

    @property
    def negative_examples(self) -> int:
        return self.true_negative + self.false_positive

    @property
    def calibrated(self) -> bool:
        return (self.positive_examples >= self.min_per_class
                and self.negative_examples >= self.min_per_class)

    def rates(self, z: float = 1.96) -> dict:
        if not self.calibrated:
            return {
                "calibrated": False,
                "positive_examples": self.positive_examples,
                "negative_examples": self.negative_examples,
                "min_per_class": self.min_per_class,
            }
        sensitivity = self.true_positive / self.positive_examples
        specificity = self.true_negative / self.negative_examples
        return {
            "calibrated": True,
            "positive_examples": self.positive_examples,
            "negative_examples": self.negative_examples,
            "sensitivity": sensitivity,
            "specificity": specificity,
            "false_positive_rate": 1.0 - specificity,
            "false_negative_rate": 1.0 - sensitivity,
            "sensitivity_wilson": wilson_interval(self.true_positive, self.positive_examples, z),
            "specificity_wilson": wilson_interval(self.true_negative, self.negative_examples, z),
            "z": z,
        }


@dataclass(frozen=True)
class EvidenceObservation:
    """One source's binary verdict about one candidate; None means unavailable."""
    source_id: str
    observed: bool | None

    def __post_init__(self) -> None:
        _nonempty(self.source_id, "source_id")
        if self.observed is not None and type(self.observed) is not bool:
            raise ValueError("observed must be True, False, or None")


@dataclass(frozen=True)
class PairwiseDependenceAssessment:
    """Pairwise correlation of source error indicators, split by true class."""
    source_a: str
    source_b: str
    calibration_set_id: str
    environment_id: str
    positive_error_phi: float | None
    positive_error_interval: tuple[float, float] | None
    positive_examples: int
    negative_error_phi: float | None
    negative_error_interval: tuple[float, float] | None
    negative_examples: int
    threshold: float
    status: str
    method: str = "phi correlation with Fisher-z approximate interval"

    def __post_init__(self) -> None:
        _nonempty(self.source_a, "source_a")
        _nonempty(self.source_b, "source_b")
        _nonempty(self.calibration_set_id, "calibration_set_id")
        _nonempty(self.environment_id, "environment_id")
        if self.source_a == self.source_b:
            raise ValueError("pairwise sources must be different")
        if self.status not in {"dependent", "no_large_correlation_detected", "uncertain"}:
            raise ValueError("invalid dependence status")
        _nonempty(self.method, "method")
        _count(self.positive_examples, "positive_examples")
        _count(self.negative_examples, "negative_examples")
        _probability(self.threshold, "threshold", open_interval=True)
        for name in ("positive_error_phi", "negative_error_phi"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not isfinite(value) or not -1.0 <= value <= 1.0):
                raise ValueError(f"{name} must be None or a finite correlation in [-1, 1]")
        for name in ("positive_error_interval", "negative_error_interval"):
            interval = getattr(self, name)
            if interval is not None:
                if (not isinstance(interval, tuple) or len(interval) != 2
                        or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x)
                               for x in interval)
                        or not -1.0 <= interval[0] <= interval[1] <= 1.0):
                    raise ValueError(f"{name} must be a valid correlation interval")

    @property
    def pair_key(self) -> tuple[str, str]:
        return tuple(sorted((self.source_a, self.source_b)))


def _phi_interval(error_a: Sequence[bool], error_b: Sequence[bool], z: float) -> tuple[float, tuple[float, float]] | None:
    """Phi correlation and Fisher-z interval for paired binary errors."""
    if len(error_a) != len(error_b) or len(error_a) < 4:
        return None
    n11 = sum(a and b for a, b in zip(error_a, error_b))
    n10 = sum(a and not b for a, b in zip(error_a, error_b))
    n01 = sum(not a and b for a, b in zip(error_a, error_b))
    n00 = sum(not a and not b for a, b in zip(error_a, error_b))
    denom = sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    if denom == 0:
        return None
    r = (n11 * n00 - n10 * n01) / denom
    clipped = min(1.0 - 1e-12, max(-1.0 + 1e-12, r))
    fisher = atanh(clipped)
    radius = z / sqrt(len(error_a) - 3)
    return r, (tanh(fisher - radius), tanh(fisher + radius))


def assess_pairwise_dependence(
    labels: Sequence[bool],
    predictions: Mapping[str, Sequence[bool]],
    source_a: str,
    source_b: str,
    *,
    calibration_set_id: str,
    environment_id: str,
    min_per_class: int = 30,
    correlation_threshold: float = 0.25,
    z: float = 1.96,
) -> PairwiseDependenceAssessment:
    """Estimate whether two sources' errors co-move on labelled calibration data.

    A no_large_correlation_detected result is not proof of independence. The
    Fisher-z interval is approximate, particularly for sparse binary errors.
    """
    _nonempty(source_a, "source_a")
    _nonempty(source_b, "source_b")
    _nonempty(calibration_set_id, "calibration_set_id")
    _nonempty(environment_id, "environment_id")
    _count(min_per_class, "min_per_class", 4)
    _probability(correlation_threshold, "correlation_threshold", open_interval=True)
    if isinstance(z, bool) or not isinstance(z, (int, float)) or not isfinite(z) or z <= 0:
        raise ValueError("z must be a positive finite number")
    if source_a == source_b:
        raise ValueError("pairwise sources must be different")
    if source_a not in predictions or source_b not in predictions:
        raise ValueError("both sources must exist in predictions")
    if any(type(label) is not bool for label in labels):
        raise ValueError("labels must contain booleans only")
    a, b = predictions[source_a], predictions[source_b]
    if len(a) != len(labels) or len(b) != len(labels):
        raise ValueError("prediction lengths must match labels")
    if any(type(x) is not bool for x in a) or any(type(x) is not bool for x in b):
        raise ValueError("predictions must contain booleans only")

    positive_indices = [i for i, label in enumerate(labels) if label]
    negative_indices = [i for i, label in enumerate(labels) if not label]
    positive_error_a = [not a[i] for i in positive_indices]
    positive_error_b = [not b[i] for i in positive_indices]
    negative_error_a = [a[i] for i in negative_indices]
    negative_error_b = [b[i] for i in negative_indices]
    pos = _phi_interval(positive_error_a, positive_error_b, z)
    neg = _phi_interval(negative_error_a, negative_error_b, z)

    enough = len(positive_indices) >= min_per_class and len(negative_indices) >= min_per_class
    if not enough or pos is None or neg is None:
        status = "uncertain"
    else:
        intervals = (pos[1], neg[1])
        clearly_dependent = any(lo > correlation_threshold or hi < -correlation_threshold
                                for lo, hi in intervals)
        clearly_small = all(lo >= -correlation_threshold and hi <= correlation_threshold
                            for lo, hi in intervals)
        status = "dependent" if clearly_dependent else "no_large_correlation_detected" if clearly_small else "uncertain"

    return PairwiseDependenceAssessment(
        source_a, source_b, calibration_set_id, environment_id,
        pos[0] if pos else None, pos[1] if pos else None, len(positive_indices),
        neg[0] if neg else None, neg[1] if neg else None, len(negative_indices),
        correlation_threshold, status,
    )


def calibrate_sources(
    labels: Sequence[bool],
    predictions: Mapping[str, Sequence[bool]],
    independence_groups: Mapping[str, str],
    *,
    calibration_set_id: str,
    environment_id: str,
    min_per_class: int = 30,
    correlation_threshold: float = 0.25,
) -> tuple[list[ReliabilityProfile], list[PairwiseDependenceAssessment]]:
    """Build source confusion profiles and pairwise dependence audits together."""
    _nonempty(calibration_set_id, "calibration_set_id")
    _nonempty(environment_id, "environment_id")
    _count(min_per_class, "min_per_class", 1)
    _probability(correlation_threshold, "correlation_threshold", open_interval=True)
    if not labels or any(type(label) is not bool for label in labels):
        raise ValueError("labels must be a non-empty boolean sequence")
    if set(predictions) != set(independence_groups):
        raise ValueError("predictions and independence_groups must have identical source IDs")
    profiles = []
    for source_id, outputs in predictions.items():
        _nonempty(source_id, "source_id")
        _nonempty(independence_groups[source_id], "independence_group")
        if len(outputs) != len(labels) or any(type(x) is not bool for x in outputs):
            raise ValueError(f"predictions for {source_id} must be a same-length boolean sequence")
        tp = fp = tn = fn = 0
        for truth, output in zip(labels, outputs):
            if truth and output:
                tp += 1
            elif truth:
                fn += 1
            elif output:
                fp += 1
            else:
                tn += 1
        profiles.append(ReliabilityProfile(
            source_id, independence_groups[source_id], calibration_set_id,
            environment_id, tp, fp, tn, fn, min_per_class,
        ))

    dependence = []
    source_ids = list(predictions)
    for i, source_a in enumerate(source_ids):
        for source_b in source_ids[i + 1:]:
            dependence.append(assess_pairwise_dependence(
                labels, predictions, source_a, source_b,
                calibration_set_id=calibration_set_id,
                environment_id=environment_id,
                min_per_class=max(4, min_per_class),
                correlation_threshold=correlation_threshold,
            ))
    return profiles, dependence


def observations_from_audit(audit: Mapping) -> list[EvidenceObservation]:
    """Collapse protocol_zero.evidence audit rows to one verdict per source.

    A source is positive only when all of its rows support the candidate, and
    negative only when all rows contradict it. Mixed, partial, or unknown rows
    become unavailable (None), never a negative vote.
    """
    if not isinstance(audit, Mapping):
        raise TypeError("audit must be a mapping")
    rows = audit.get("evidence")
    if not isinstance(rows, (list, tuple)):
        raise ValueError("audit.evidence must be a sequence")
    grouped: dict[str, list[str]] = {}
    allowed = {"supported", "contradicted", "partial", "unknown"}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each evidence row must be a mapping")
        source_id = row.get("source_id")
        status = row.get("status")
        _nonempty(source_id, "evidence source_id")
        if not isinstance(status, str) or status not in allowed:
            raise ValueError(f"unsupported evidence status: {status}")
        grouped.setdefault(source_id, []).append(status)
    out = []
    for source_id, statuses in grouped.items():
        if all(status == "supported" for status in statuses):
            observed = True
        elif all(status == "contradicted" for status in statuses):
            observed = False
        else:
            observed = None
        out.append(EvidenceObservation(source_id, observed))
    return out


def _likelihood_ratio_interval(profile: ReliabilityProfile, observed: bool, z: float) -> tuple[float, float]:
    rates = profile.rates(z)
    if not rates["calibrated"]:
        raise ValueError("cannot calculate a likelihood ratio from uncalibrated evidence")
    sens_lo, sens_hi = rates["sensitivity_wilson"]
    spec_lo, spec_hi = rates["specificity_wilson"]
    if observed:
        lower = sens_lo / max(_EPS, 1.0 - spec_lo)
        upper = sens_hi / max(_EPS, 1.0 - spec_hi)
    else:
        lower = (1.0 - sens_hi) / max(_EPS, spec_hi)
        upper = (1.0 - sens_lo) / max(_EPS, spec_lo)
    return max(_EPS, lower), max(_EPS, upper)


def _logistic(log_odds: float) -> float:
    if log_odds >= 0:
        return 1.0 / (1.0 + exp(-min(log_odds, 745.0)))
    e = exp(max(log_odds, -745.0))
    return e / (1.0 + e)


def evaluate_hypothesis(
    observations: Sequence[EvidenceObservation],
    profiles: Sequence[ReliabilityProfile],
    *,
    evaluation_set_id: str,
    evaluation_environment_id: str,
    prior_probability: float = 0.5,
    confidence_level: float = 0.95,
    accept_threshold: float = 0.95,
    reject_threshold: float = 0.05,
    min_provenance_groups: int = 2,
    dependence_assessments: Sequence[PairwiseDependenceAssessment] = (),
    require_dependence_audit: bool = True,
) -> dict:
    """Fuse calibrated source verdicts and abstain when evidence is inadequate.

    Calibration and evaluation set identifiers must differ. Each usable
    provenance group contributes at most one observation. If dependence audit
    is required, every used source pair must have a same-calibration assessment
    whose interval does not indicate large error correlation.
    """
    _nonempty(evaluation_set_id, "evaluation_set_id")
    _nonempty(evaluation_environment_id, "evaluation_environment_id")
    _probability(prior_probability, "prior_probability", open_interval=True)
    _probability(confidence_level, "confidence_level", open_interval=True)
    _probability(accept_threshold, "accept_threshold", open_interval=True)
    _probability(reject_threshold, "reject_threshold", open_interval=True)
    if reject_threshold >= 0.5 or accept_threshold <= 0.5 or reject_threshold >= accept_threshold:
        raise ValueError("require reject_threshold < 0.5 < accept_threshold")
    _count(min_provenance_groups, "min_provenance_groups", 1)
    if type(require_dependence_audit) is not bool:
        raise ValueError("require_dependence_audit must be a boolean")

    profile_map: dict[str, ReliabilityProfile] = {}
    for profile in profiles:
        if not isinstance(profile, ReliabilityProfile):
            raise TypeError("profiles must contain ReliabilityProfile objects")
        if profile.source_id in profile_map:
            raise ValueError(f"duplicate reliability profile: {profile.source_id}")
        profile_map[profile.source_id] = profile

    seen_sources: set[str] = set()
    seen_groups: set[str] = set()
    usable = []
    skipped = []
    for observation in observations:
        if not isinstance(observation, EvidenceObservation):
            raise TypeError("observations must contain EvidenceObservation objects")
        if observation.source_id in seen_sources:
            raise ValueError(f"duplicate observation from source: {observation.source_id}")
        seen_sources.add(observation.source_id)
        profile = profile_map.get(observation.source_id)
        if profile is None:
            skipped.append({"source_id": observation.source_id, "reason": "missing_calibration_profile"})
            continue
        if profile.calibration_set_id == evaluation_set_id:
            raise ValueError(f"calibration/evaluation data leakage for source: {profile.source_id}")
        if profile.environment_id != evaluation_environment_id:
            skipped.append({"source_id": observation.source_id, "reason": "environment_mismatch",
                            "calibration_environment_id": profile.environment_id,
                            "evaluation_environment_id": evaluation_environment_id})
            continue
        if observation.observed is None:
            skipped.append({"source_id": observation.source_id, "reason": "observation_unavailable"})
            continue
        if not profile.calibrated:
            skipped.append({
                "source_id": observation.source_id,
                "reason": "insufficient_calibration",
                "positive_examples": profile.positive_examples,
                "negative_examples": profile.negative_examples,
                "min_per_class": profile.min_per_class,
            })
            continue
        if profile.independence_group in seen_groups:
            raise ValueError(
                "multiple usable observations share independence group: "
                f"{profile.independence_group}; pre-aggregate or select one source"
            )
        seen_groups.add(profile.independence_group)
        usable.append((profile, observation.observed))

    group_count = len(usable)
    alpha = 1.0 - confidence_level
    tail = alpha / (4.0 * group_count) if group_count else alpha / 4.0
    quantile = 1.0 - tail
    if quantile >= 1.0:
        raise ValueError("confidence_level is too close to 1 for numerical resolution")
    z = NormalDist().inv_cdf(quantile)

    used = []
    for profile, observed in usable:
        lr_lo, lr_hi = _likelihood_ratio_interval(profile, observed, z)
        if lr_lo > 1.0:
            direction = "supports_candidate"
        elif lr_hi < 1.0:
            direction = "opposes_candidate"
        else:
            direction = "inconclusive"
        used.append({
            "source_id": profile.source_id,
            "independence_group": profile.independence_group,
            "observed_support": observed,
            "direction": direction,
            "likelihood_ratio_interval": [lr_lo, lr_hi],
            "calibration": profile.rates(z),
        })

    dependence_map = {}
    for assessment in dependence_assessments:
        if not isinstance(assessment, PairwiseDependenceAssessment):
            raise TypeError("dependence_assessments must contain PairwiseDependenceAssessment objects")
        if assessment.pair_key in dependence_map:
            raise ValueError(f"duplicate pairwise dependence assessment: {assessment.pair_key}")
        dependence_map[assessment.pair_key] = assessment

    dependence_checks = []
    dependence_block = None
    if require_dependence_audit and group_count > 1:
        for i, (profile_a, _) in enumerate(usable):
            for profile_b, _ in usable[i + 1:]:
                key = tuple(sorted((profile_a.source_id, profile_b.source_id)))
                assessment = dependence_map.get(key)
                if assessment is None:
                    dependence_checks.append({"sources": list(key), "status": "missing"})
                    dependence_block = dependence_block or "dependence_audit_missing"
                    continue
                if (assessment.calibration_set_id != profile_a.calibration_set_id
                        or assessment.calibration_set_id != profile_b.calibration_set_id
                        or assessment.environment_id != profile_a.environment_id
                        or assessment.environment_id != profile_b.environment_id):
                    dependence_checks.append({"sources": list(key), "status": "calibration_or_environment_mismatch"})
                    dependence_block = dependence_block or "dependence_audit_mismatch"
                    continue
                dependence_checks.append({"sources": list(key), "status": assessment.status,
                                          "positive_error_phi": assessment.positive_error_phi,
                                          "positive_error_interval": assessment.positive_error_interval,
                                          "negative_error_phi": assessment.negative_error_phi,
                                          "negative_error_interval": assessment.negative_error_interval,
                                          "threshold": assessment.threshold})
                if assessment.status == "dependent":
                    dependence_block = "calibration_detected_correlated_errors"
                elif assessment.status != "no_large_correlation_detected":
                    dependence_block = dependence_block or "dependence_audit_uncertain"

    log_prior_odds = log(prior_probability / (1.0 - prior_probability))
    log_lower = log_prior_odds + sum(log(row["likelihood_ratio_interval"][0]) for row in used)
    log_upper = log_prior_odds + sum(log(row["likelihood_ratio_interval"][1]) for row in used)
    posterior_lower = _logistic(log_lower)
    posterior_upper = _logistic(log_upper)

    if group_count < min_provenance_groups:
        decision, reason = "abstain", "insufficient_distinct_calibrated_provenance_groups"
    elif dependence_block is not None:
        decision, reason = "abstain", dependence_block
    elif posterior_lower >= accept_threshold:
        decision, reason = "support", "posterior_lower_bound_reaches_accept_threshold"
    elif posterior_upper <= reject_threshold:
        decision, reason = "reject", "posterior_upper_bound_below_reject_threshold"
    else:
        decision, reason = "abstain", "evidence_interval_does_not_clear_a_decision_threshold"

    return {
        "decision": decision,
        "reason": reason,
        "posterior_envelope": [posterior_lower, posterior_upper],
        "prior_probability": prior_probability,
        "confidence_level": confidence_level,
        "bonferroni_wilson_z": z,
        "evaluation_environment_id": evaluation_environment_id,
        "accept_threshold": accept_threshold,
        "reject_threshold": reject_threshold,
        "provenance_group_count": group_count,
        "min_provenance_groups": min_provenance_groups,
        "used_evidence": used,
        "skipped_evidence": skipped,
        "dependence_audit_required": require_dependence_audit,
        "dependence_checks": dependence_checks,
        "integrity_verified": False,
        "assumptions": [
            "calibration and evaluation set identifiers are distinct; actual sample disjointness is not independently verified",
            "one observation per declared provenance group",
            "distinct provenance groups are assumed conditionally independent unless a calibration dependence audit blocks the decision; independence is never proven",
            "Bonferroni correction covers the per-source sensitivity/specificity Wilson intervals under the binomial calibration model",
            "the posterior envelope still depends on the declared conditional-independence model and prior; it is not a guarantee of real-world accuracy",
            "matching environment identifiers are user-supplied and do not prove the physical environments are equivalent",
            "pairwise phi/Fisher-z dependence checks are approximate and can miss nonlinear or time-varying dependencies",
        ],
    }
