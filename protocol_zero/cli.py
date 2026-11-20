from __future__ import annotations
import argparse, json
from pathlib import Path
from .pipeline import analyze


def main():
    ap = argparse.ArgumentParser(description="PROTOCOL ZERO V0.2.1 bounded binary stream inference prototype")
    ap.add_argument("--train", nargs="+", required=True, help="training binary capture(s)")
    ap.add_argument("--validation", nargs="+", required=True, help="validation binary capture(s)")
    ap.add_argument("--test", nargs="+", required=True, help="test binary capture(s)")
    ap.add_argument("--out", default="protocol_zero_v02_result.json")
    ap.add_argument("--repair", action="store_true", help="emit conditional repair hypotheses (never trusted)")
    args = ap.parse_args()
    load = lambda paths: [Path(p).read_bytes() for p in paths]
    result = analyze(load(args.train), load(args.validation), load(args.test), repair=args.repair)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "model": result["model"], "frames": sum(len(x["frames"]) for x in result.get("decoded", [])), "suspects": sum(len(x["suspects"]) for x in result.get("decoded", [])), "fields": result.get("fields", [])}, indent=2))

if __name__ == "__main__":
    main()
