#!/usr/bin/env python3
"""Validate an Evidence Bundle against the V1 JSON Schema and cross-reference rules."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "protocol-zero-evidence-v1.schema.json"
DEFAULT_FIXTURE = ROOT / "examples" / "evidence_bundle_v1_minimal.json"


def _unique_ids(rows: list[dict[str, Any]], key: str, label: str, errors: list[str]) -> set[str]:
    found: set[str] = set()
    for index, row in enumerate(rows):
        value = row.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{label}[{index}] has no valid {key}")
        elif value in found:
            errors.append(f"duplicate {label} {key}: {value}")
        else:
            found.add(value)
    return found


def cross_reference_errors(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    keys = {
        "captures": "capture_id",
        "sources": "source_id",
        "flows": "flow_id",
        "sessions": "session_id",
        "messages": "message_id",
        "message_families": "message_family_id",
        "evidence": "evidence_id",
        "frame_hypotheses": "hypothesis_id",
        "field_hypotheses": "hypothesis_id",
        "relation_hypotheses": "hypothesis_id",
        "semantic_hypotheses": "hypothesis_id",
        "state_models": "state_model_id",
        "calibration_profiles": "profile_id",
        "dependence_audits": "audit_id",
        "drift_assessments": "assessment_id",
        "repair_hypotheses": "repair_id",
        "validation_results": "validation_id",
    }
    ids: dict[str, set[str]] = {
        collection: _unique_ids(bundle.get(collection, []), key, collection, errors)
        for collection, key in keys.items()
    }
    all_ids = set().union(*ids.values()) if ids else set()

    # IDs are globally unique across entity types, not merely within each array.
    owners: dict[str, str] = {}
    for collection, key in keys.items():
        for row in bundle.get(collection, []):
            value = row.get(key)
            if isinstance(value, str) and value:
                previous = owners.get(value)
                if previous is not None and previous != collection:
                    errors.append(f"ID {value} is reused by {previous} and {collection}")
                owners[value] = collection

    captures = {x["capture_id"]: x for x in bundle.get("captures", [])}
    evidence_ids = ids["evidence"]

    for source in bundle.get("sources", []):
        ref = source.get("capture_id")
        if ref is not None and ref not in ids["captures"]:
            errors.append(f"source {source.get('source_id')} references unknown capture {ref}")

    for flow in bundle.get("flows", []):
        if flow.get("capture_id") not in ids["captures"]:
            errors.append(f"flow {flow.get('flow_id')} references unknown capture")

    for session in bundle.get("sessions", []):
        for ref in session.get("flow_ids", []):
            if ref not in ids["flows"]:
                errors.append(f"session {session.get('session_id')} references unknown flow {ref}")

    for message in bundle.get("messages", []):
        mid = message.get("message_id")
        if message.get("session_id") not in ids["sessions"]:
            errors.append(f"message {mid} references unknown session")
        if message.get("flow_id") not in ids["flows"]:
            errors.append(f"message {mid} references unknown flow")
        content_ref = message.get("content_ref", {})
        capture = captures.get(content_ref.get("capture_id"))
        if capture is None:
            errors.append(f"message {mid} references unknown content capture")
        else:
            offset = content_ref.get("byte_offset", 0)
            length = content_ref.get("byte_length", 0)
            if offset + length > capture.get("size_bytes", 0):
                errors.append(f"message {mid} content_ref exceeds capture size")
        if message.get("byte_length") != content_ref.get("byte_length"):
            errors.append(f"message {mid} byte_length differs from content_ref")
        for ref in message.get("frame_hypothesis_ids", []):
            if ref not in ids["frame_hypotheses"]:
                errors.append(f"message {mid} references unknown frame hypothesis {ref}")

    for family in bundle.get("message_families", []):
        for ref in family.get("member_message_ids", []):
            if ref not in ids["messages"]:
                errors.append(f"message family {family.get('message_family_id')} references unknown message {ref}")

    for item in bundle.get("evidence", []):
        if item.get("source_id") not in ids["sources"]:
            errors.append(f"evidence {item.get('evidence_id')} references unknown source")
        if item.get("target_ref") not in all_ids:
            errors.append(f"evidence {item.get('evidence_id')} references unknown target")

    for collection in ("frame_hypotheses", "field_hypotheses", "relation_hypotheses"):
        for hypothesis in bundle.get(collection, []):
            hid = hypothesis.get("hypothesis_id")
            for key in ("support_evidence_ids", "contradiction_evidence_ids"):
                for ref in hypothesis.get(key, []):
                    if ref not in evidence_ids:
                        errors.append(f"hypothesis {hid} references unknown evidence {ref}")
            for ref in hypothesis.get("alternative_ids", []):
                if ref not in all_ids:
                    errors.append(f"hypothesis {hid} references unknown alternative {ref}")
            if collection == "relation_hypotheses":
                for ref in hypothesis.get("operand_ids", []):
                    if ref not in ids["field_hypotheses"]:
                        errors.append(f"relation hypothesis {hid} references unknown field operand {ref}")

    for frame in bundle.get("frame_hypotheses", []):
        if frame.get("scope_ref") not in all_ids:
            errors.append(f"frame hypothesis {frame.get('hypothesis_id')} references unknown scope")

    for field in bundle.get("field_hypotheses", []):
        if field.get("message_family_ref") not in ids["message_families"]:
            errors.append(f"field hypothesis {field.get('hypothesis_id')} references unknown message family")

    for semantic in bundle.get("semantic_hypotheses", []):
        if semantic.get("field_hypothesis_id") not in ids["field_hypotheses"]:
            errors.append(f"semantic hypothesis {semantic.get('hypothesis_id')} references unknown field")
        for ref in semantic.get("evidence_ids", []):
            if ref not in evidence_ids:
                errors.append(f"semantic hypothesis {semantic.get('hypothesis_id')} references unknown evidence {ref}")

    for model in bundle.get("state_models", []):
        if model.get("message_family_ref") not in ids["message_families"]:
            errors.append(f"state model {model.get('state_model_id')} references unknown message family")
        state_ids = {x.get("state_id") for x in model.get("states", [])}
        if model.get("initial_state_id") not in state_ids:
            errors.append(f"state model {model.get('state_model_id')} has unknown initial state")
        for ref in model.get("training_session_ids", []) + model.get("validation_session_ids", []):
            if ref not in ids["sessions"]:
                errors.append(f"state model {model.get('state_model_id')} references unknown session {ref}")
        for transition in model.get("transitions", []):
            if transition.get("from_state") not in state_ids or transition.get("to_state") not in state_ids:
                errors.append(f"state model {model.get('state_model_id')} has transition to unknown state")
            for ref in transition.get("evidence_ids", []):
                if ref not in evidence_ids:
                    errors.append(f"state model {model.get('state_model_id')} transition references unknown evidence {ref}")

    profiles = {x["profile_id"]: x for x in bundle.get("calibration_profiles", [])}
    for profile in bundle.get("calibration_profiles", []):
        if profile.get("source_id") not in ids["sources"]:
            errors.append(f"calibration profile {profile.get('profile_id')} references unknown source")
        positive = profile.get("true_positive", 0) + profile.get("false_negative", 0)
        negative = profile.get("true_negative", 0) + profile.get("false_positive", 0)
        minimum = profile.get("min_per_class", 1)
        if profile.get("calibrated") and (positive < minimum or negative < minimum):
            errors.append(f"calibration profile {profile.get('profile_id')} is marked calibrated below its sample minimum")

    for audit in bundle.get("dependence_audits", []):
        if audit.get("source_a") not in ids["sources"] or audit.get("source_b") not in ids["sources"]:
            errors.append(f"dependence audit {audit.get('audit_id')} references unknown source")
        if audit.get("source_a") == audit.get("source_b"):
            errors.append(f"dependence audit {audit.get('audit_id')} must compare two distinct sources")

    for drift in bundle.get("drift_assessments", []):
        if drift.get("source_id") not in ids["sources"]:
            errors.append(f"drift assessment {drift.get('assessment_id')} references unknown source")
        profile = profiles.get(drift.get("calibration_profile_id"))
        if profile is None:
            errors.append(f"drift assessment {drift.get('assessment_id')} references unknown calibration profile")
        else:
            if profile.get("source_id") != drift.get("source_id"):
                errors.append(f"drift assessment {drift.get('assessment_id')} source differs from calibration profile")
            if profile.get("calibration_dataset_id") == drift.get("evaluation_dataset_id"):
                errors.append(f"drift assessment {drift.get('assessment_id')} reuses calibration dataset for evaluation")
            if profile.get("environment_id") != drift.get("environment_id") and drift.get("status") != "abstain":
                errors.append(f"drift assessment {drift.get('assessment_id')} has environment mismatch without abstention")

    for repair in bundle.get("repair_hypotheses", []):
        if repair.get("original_message_id") not in ids["messages"]:
            errors.append(f"repair hypothesis {repair.get('repair_id')} references unknown original message")
        for ref in repair.get("evidence_ids", []):
            if ref not in evidence_ids:
                errors.append(f"repair hypothesis {repair.get('repair_id')} references unknown evidence {ref}")
        if repair.get("trusted_as_original") is not False:
            errors.append(f"repair hypothesis {repair.get('repair_id')} cannot be trusted as original")

    for collection in ("frame_hypotheses", "field_hypotheses", "relation_hypotheses", "semantic_hypotheses", "repair_hypotheses"):
        for item in bundle.get(collection, []):
            score = item.get("score", {})
            profile_id = score.get("calibration_profile_id")
            if profile_id is not None and profile_id not in ids["calibration_profiles"]:
                label = item.get("hypothesis_id", item.get("repair_id"))
                errors.append(f"{collection} item {label} references unknown calibration profile")

    for result in bundle.get("validation_results", []):
        for ref in result.get("target_hypothesis_ids", []):
            if ref not in all_ids:
                errors.append(f"validation {result.get('validation_id')} references unknown target {ref}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"schema: {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in validator.iter_errors(bundle)
    ]
    errors.extend(f"reference: {message}" for message in cross_reference_errors(bundle))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"valid: {args.bundle}")
    print(f"schema: {args.schema}")
    print("cross-references: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
