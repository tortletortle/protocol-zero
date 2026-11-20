from __future__ import annotations
from .framing import infer_model, decode_stream
from .fields import infer_fields


def analyze(training_streams: list[bytes], validation_streams: list[bytes], test_streams: list[bytes], *, repair: bool = False) -> dict:
    fit = infer_model(training_streams, validation_streams)
    if fit["status"] != "accepted":
        return {"status": fit["status"], "model": None, "fit": fit, "decoded": [], "fields": []}
    model = fit["model"]
    decoded = [decode_stream(stream, model, i) for i, stream in enumerate(test_streams)]
    frames = [r for result in decoded for r in result["frames"]]
    fields = infer_fields(frames, model)
    repair_logs = []
    if repair:
        from .repair import learn_profiles, repair_stream
        profiles = learn_profiles(training_streams, validation_streams, model)
        repair_logs = [repair_stream(stream, model, profiles, i, decoded[i]) for i, stream in enumerate(test_streams)]
    return {
        "status": "accepted",
        "model": model.to_dict(),
        "fit": {k: v for k, v in fit.items() if k not in ("model", "candidates")},
        "decoded": [
            {"frames": [r.to_dict() for r in d["frames"]], "suspects": [r.to_dict() for r in d["suspects"]]}
            for d in decoded
        ],
        "fields": [f.to_dict() for f in fields],
        **({"repair_hypotheses": repair_logs} if repair else {}),
    }
