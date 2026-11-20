# PROTOCOL ZERO V0.2

**Purpose:** infer a bounded binary-frame model from raw byte-stream captures, recover frame boundaries under variable payload lengths and byte-level noise, and produce auditable field hypotheses.

V0.2 is an integrated research prototype, not a general-purpose protocol reverse-engineering product. It deliberately abstains when the observed checksum/layout does not fit its supported model family.

## What changed from the restored V0.11 research snapshot

- Integrates framing, validation, decoding, and field inference into one pipeline.
- Scans the entire capture for a 2-byte sync word instead of assuming the capture begins at a frame boundary.
- Searches 1-byte and 2-byte length fields, including big-/little-endian 2-byte lengths and small fixed fields between length and payload.
- Supports variable-length payloads and non-overlapping frame selection by weighted interval scheduling.
- Validates checksum hypotheses on separate captures; checksum-failed candidates are reported as `suspect`, never silently promoted to trusted frames.
- Recovers constant, enum, length, counter-candidate, payload, and checksum field hypotheses.
- Keeps ambiguous/unsupported layouts as `ambiguous` or `rejected` instead of forcing a protocol guess.
- Preserves the V0.11 source snapshot under `legacy/v0.11/` for regression and comparison.

## Supported input and current search space

Input is a byte stream that has already been converted from the physical signal into bytes. V0.2 does **not** yet demodulate SDR/IQ samples, decode UART start/stop/parity bits, infer baud rate, or parse CAN electrical waveforms.

The current model family is intentionally bounded:

- 2-byte sync word.
- Length field at relative offsets 2–5; width 1 or 2 bytes; 2-byte length supports both endian orders.
- 0–2 fixed bytes between the length field and payload.
- Length value equals payload byte count.
- One-byte trailer.
- Checksum candidates: `sum8`, `xor8`, `crc8_smbus`, `crc8_j1850`, `crc8_autosar`.
- Maximum inferred payload length: 512 bytes.

A checksum mismatch is evidence of corruption or a wrong model. V0.2 flags such frames as suspects; it does not repair them. Byte deletion inside a frame can prevent recovery of that frame, although the scanner can resynchronize at a later sync word.

## Run

Python 3.10+; standard library only.

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s legacy/v0.11 -v
python -m compileall -q protocol_zero
python experiments/run_benchmark.py
```

For your own captures:

```bash
python -m protocol_zero.cli --train captures/train_a.bin captures/train_b.bin \
  --validation captures/validation.bin \
  --test captures/test.bin \
  --out protocol_zero_result.json
```

The CLI writes the model, decoded frames, suspects, and field hypotheses as JSON. It does not overwrite source captures.

## Architecture

```text
byte-stream captures
        │
        ▼
2-byte sync candidate discovery
        │
        ▼
length-layout hypothesis search
        │
        ▼
checksum validation on held-out captures
        │
        ▼
weighted non-overlapping frame selection
        │
        ├── trusted frames (checksum passes)
        └── suspects (boundary plausible, checksum fails)
        │
        ▼
field hypotheses + evidence
        │
        ▼
JSON report
```

Core modules:

- `protocol_zero/framing.py`: sync/length/checksum model search, validation gate, frame extraction, interval selection.
- `protocol_zero/fields.py`: field-boundary and field-type hypotheses.
- `protocol_zero/checksums.py`: explicit checksum registry.
- `protocol_zero/pipeline.py`: end-to-end orchestration.
- `protocol_zero/synthetic.py`: controlled synthetic captures with ground truth.
- `experiments/run_benchmark.py`: independent-seed comparison against the restored V0.11 framing and field heuristics.

## V0.2 synthetic benchmark

See [`docs/V0.2_REPORT.md`](docs/V0.2_REPORT.md), [`docs/V0.2_THRESHOLD_PILOT.md`](docs/V0.2_THRESHOLD_PILOT.md), and `experiments/v02_benchmark.json`.

The benchmark has 100 runs: 20 independent seeds each for clean, shifted/noisy-gap, bit-corrupted, combined corruption/deletion, and unsupported-checksum conditions. A separate six-seed pilot selected the 0.70 checksum-consistency threshold; pilot seeds 20100–20105 and holdout seeds 20400–20419 are disjoint. Training, validation, and test captures also use disjoint seeds.

Headline results on this synthetic protocol family:

- Exact model recovery: 20/20 in clean and shifted conditions; 19/20 in noisy and combined conditions.
- Overall clean-frame boundary F1: 1.000 in clean/shifted and 0.950 in noisy/combined. All accepted runs have F1 = 1.000; the 0.950 aggregate reflects one conservative abstention in each noisy condition.
- V0.11 DP baseline clean-frame F1: 0.916–0.920 across the supported conditions.
- Corrupted-frame suspect precision/recall: 1.000/0.950 overall for bit-corruption-only; 1.000/0.799 overall for combined corruption and byte deletion (0.841 recall conditional on accepted runs).
- Required field-boundary/type recall: 1.000 conditional on accepted V0.2 runs; 0.950 overall in noisy/combined conditions. The V0.11 field heuristic reaches 0.380 overall in those conditions.
- Unsupported checksum: V0.2 correctly rejects 20/20; the legacy no-checksum mode accepts false structures and obtains zero exact frame F1.

These are controlled synthetic results, not real-device validation or evidence of generalization to arbitrary protocols.

## Known limitations / next research gates

1. Expand sync-word inference beyond 2 bytes and avoid overfitting repeated payload tokens.
2. Add length semantics beyond `payload_length`, including total-length and length-with-header variants.
3. Add CRC-16 and parameter search with explicit complexity penalties; do not silently accept arbitrary checksum fits.
4. Improve byte insertion/deletion alignment and measure frame-boundary recovery separately from checksum integrity.
5. Add message-type clustering and counter-aware sequence grouping.
6. Compare field inference against NEMESYS-style intra-message structure and NetPlier-style multi-message alignment on public traces.
7. Add real UART/CAN captures with provenance and a frozen held-out evaluation protocol.
8. Calibrate field confidence scores; current values are heuristic support scores, not calibrated probabilities.

## Engineering policy

- Unknown or unsupported protocol families must be rejected or marked ambiguous.
- Only checksum-verified frames are used for trusted field inference.
- Synthetic results must be labelled synthetic.
- Never claim real-world accuracy without a separately sourced and held-out capture set.
- The V0.11 snapshot is retained unchanged under `legacy/v0.11/`.

## V0.2.1 — conditional damage reconstruction

Optional `--repair` emits separate, untrusted reconstruction hypotheses. It
uses reversible checksum states, an independently validated empirical payload
profile, and a competing checksum-byte flip explanation. Original decoded
frames and fields are unchanged. See `docs/V0.2.1_REPORT.md` for measured
coverage and counterexamples. The conditional unique result is **not** proof
of original bytes. Never automatically apply repairs.

```bash
python -m unittest discover -s tests -v
python experiments/repair_benchmark.py
python -m protocol_zero --train train.bin --validation validation.bin --test test.bin --repair --out result.json
```
