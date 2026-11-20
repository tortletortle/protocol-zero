from __future__ import annotations
import json, statistics, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol_zero.framing import infer_model
from protocol_zero.synthetic import make_capture

GROUPS = ("clean", "shifted", "noisy", "combined", "unknown")
SEEDS = range(20100, 20106)  # pilot only; disjoint from confirmatory holdout
THRESHOLDS = (0.65, 0.70)

def truth_model(model):
    return bool(model and model.sync == b"\xD5\x7E" and model.length_offset == 3 and model.length_width == 1 and model.payload_offset == 5 and model.checksum == "crc8_smbus")

def run_one(group, seed, threshold):
    unknown = group == "unknown"
    noise = "noisy" if group in ("noisy", "combined") else "clean"
    train = [make_capture(seed+i*101, 55, noise=noise, unknown_checksum=unknown) for i in range(2)]
    val = [make_capture(seed+303, 35, noise=noise, unknown_checksum=unknown)]
    fit = infer_model([x.data for x in train], [x.data for x in val], min_checksum_rate=threshold)
    return {"group":group,"seed":seed,"threshold":threshold,"status":fit["status"],"exact":truth_model(fit.get("model"))}

def main():
    rows = []
    for t in THRESHOLDS:
        for g in GROUPS:
            for s in SEEDS:
                rows.append(run_one(g,s,t))
            print(f"pilot threshold={t:.2f} group={g} complete", flush=True)
    summary = {}
    for t in THRESHOLDS:
        summary[str(t)] = {g:{
            "accept_rate":statistics.mean(r["status"] == "accepted" for r in rows if r["threshold"]==t and r["group"]==g),
            "exact_model_rate":statistics.mean(r["exact"] for r in rows if r["threshold"]==t and r["group"]==g),
        } for g in GROUPS}
    eligible=[]
    for t in THRESHOLDS:
        supported=[summary[str(t)][g]["exact_model_rate"] for g in GROUPS if g!="unknown"]
        false_accept=summary[str(t)]["unknown"]["accept_rate"]
        if min(supported) >= 0.90 and false_accept == 0:
            eligible.append(t)
    chosen=max(eligible) if eligible else None
    out={"title":"V0.2 checksum-threshold pilot","pilot_seeds":list(SEEDS),"holdout_seeds_excluded":[20400,20419],"thresholds":list(THRESHOLDS),"selection_rule":"Choose the highest threshold with >=90% exact-model recovery in every supported pilot condition and zero acceptance in the unsupported-checksum pilot condition.","chosen_threshold":chosen,"summary":summary,"rows":rows}
    (ROOT/"experiments"/"v02_threshold_pilot.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps({"chosen_threshold":chosen,"summary":summary},indent=2))
if __name__=="__main__":main()
