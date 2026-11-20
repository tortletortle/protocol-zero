# Changelog

## V0.2.0

- Integrated sync-word, variable-length, length-offset, and checksum model search.
- Added separate train/validation gating and conservative ambiguity/rejection behavior.
- Added weighted interval scheduling for overlapping frame candidates.
- Added trusted-frame and checksum-suspect output channels.
- Added constant, enum, length, counter-candidate, payload, and checksum field hypotheses.
- Added 1-/2-byte length support, including big-endian 2-byte length.
- Added independent synthetic benchmark and V0.11 framing/field baselines.
- Preserved restored V0.11 source snapshot under `legacy/v0.11/`.

## 0.2.1
- Add bounded single-edit reconstruction, reversible checksum states and explicit alternatives.
- Learn length-conditioned payload invariants on separate training and validation traces.
- Add opt-in CLI output; never promote reconstruction hypotheses to trusted frames.
- Retain V0.2 and V0.11 records; add exploratory and independent-seed synthetic controls.
