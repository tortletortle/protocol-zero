"""Reproduce a constructive CRC-8 collision and a uniform-padding null trial."""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path

from protocol_zero.crc_discovery import CRCModel
from protocol_zero.integrity import crc_collision_baseline, make_crc8_collision_witness


def run(trials: int = 50_000, seed: int = 82_607) -> dict:
    if trials <= 0:
        raise ValueError("trials must be positive")
    rng = random.Random(seed)
    model = CRCModel(0x07, 0, 0)
    matches = 0
    for _ in range(trials):
        payload = rng.randbytes(32)
        delete_index = rng.randrange(len(payload))
        prefix = bytes([0xAA, 0x55, 0x04, 32, 0x20])
        original_crc = model.predict(prefix + payload)
        shortened = payload[:delete_index] + payload[delete_index + 1:]
        candidate_body = prefix + shortened + bytes([original_crc])
        random_padding = rng.randrange(256)
        matches += random_padding == model.predict(candidate_body)

    baseline = crc_collision_baseline(8)["uniform_random_false_match_baseline"]
    observed = matches / trials
    witness = make_crc8_collision_witness(
        bytes([0xAA, 0x55, 0x04, 16, 0x20]),
        bytes(range(1, 17)),
        model,
        5,
    )
    return {
        "trials": trials,
        "seed": seed,
        "uniform_random_padding_matches": matches,
        "observed_rate": observed,
        "expected_uniform_rate": baseline,
        "expected_matches": trials * baseline,
        "constructive_witness": witness,
        "scope": (
            "one fixed known CRC-8 model and one candidate checksum byte; "
            "padding is independently uniform. This is not a false-acceptance "
            "estimate for model search, structured traffic, or real captures."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=82_607)
    parser.add_argument("--out", default="experiments/v026_collision_summary.json")
    args = parser.parse_args()
    result = run(args.trials, args.seed)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "trials": result["trials"],
        "matches": result["uniform_random_padding_matches"],
        "observed_rate": result["observed_rate"],
        "expected_uniform_rate": result["expected_uniform_rate"],
        "witness_same_observation": result["constructive_witness"]["same_observed_bytes"],
    }, indent=2))


if __name__ == "__main__":
    main()
