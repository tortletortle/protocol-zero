# Open-source reuse and baseline review

This review informs architecture and benchmarking. No external project source code is copied into the V0.2 implementation.

| Project / method | Relevant capability | V0.2 decision |
|---|---|---|
| Netzob | Protocol vocabulary and grammar inference, passive/active inference, traffic generation and fuzzing; variable-length fields are in scope. | Use as a future end-to-end grammar/model baseline. Do not embed its GPLv3 code in this prototype; evaluate separately and record version/dependencies. |
| NetPlier | Multiple sequence alignment plus probabilistic inference for keyword/message-type fields and protocol format/state-machine recovery. | Use as a field/message clustering baseline on supported network traces; it depends on Netzob and MAFFT and is not a raw UART demodulator. |
| NEMESYS | Infers field boundaries from byte-value change distributions within individual messages and proposes Format Match Score. | Use its intra-message boundary score as a future field-inference baseline; do not claim our current heuristic is equivalent. |
| Universal Radio Hacker (URH) | SDR signal import, modulation/demodulation, decoding and rule-based protocol field analysis. | Treat as a possible RF acquisition/bit-decoding front end. The original repository is archived and GPL-3.0; no code is embedded. |
| Kaitai Struct | Declarative binary format descriptions and parser generation. | Target export format after a schema has enough evidence; it is not a schema inference engine. |

## Why the custom V0.2 code still exists

The current prototype targets an intermediate representation: an already-decoded byte stream from a UART-like bus, with a narrow and explicit frame hypothesis family. Existing frameworks cover broader workflow layers, but their assumptions, dependencies, licensing, and input formats differ. V0.2 therefore keeps a small deterministic core and uses external tools as comparison targets rather than silently importing a large dependency stack.

## References

- Netzob documentation and GPLv3 notice: https://netzob.readthedocs.io/en/latest/
- NetPlier source and installation requirements: https://github.com/yapengye/netplier
- NetPlier paper: https://www.ndss-symposium.org/ndss-paper/netplier-probabilistic-network-protocol-reverse-engineering-from-message-traces/
- NEMESYS paper: https://www.usenix.org/conference/woot18/presentation/kleber
- URH source repository (archived): https://github.com/jopohl/urh
- Kaitai Struct: https://kaitai.io/
