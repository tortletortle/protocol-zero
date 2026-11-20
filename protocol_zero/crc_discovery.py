"""Bounded CRC-8 discovery on independently delimited, clean codewords.

Non-reflected, odd polynomial, whole body followed by one CRC byte.
No transmission or modification of captures; exact evidence, not probabilities.
"""
from dataclasses import dataclass, asdict
from functools import lru_cache
from collections import Counter
from pathlib import Path
import argparse
import json
from .checksums import CHECKSUMS

MAX_BODY = 512
MAX_SAMPLES = 512

@lru_cache(maxsize=128)
def table(poly):
    out = []
    for x in range(256):
        for _ in range(8):
            x = ((x << 1) ^ (poly if x & 128 else 0)) & 255
        out.append(x)
    return tuple(out)

@dataclass(frozen=True, order=True)
class CRCModel:
    poly: int
    init: int
    xorout: int

    def __post_init__(self):
        if not (0 < self.poly < 256 and self.poly % 2 and 0 <= self.init < 256 and 0 <= self.xorout < 256):
            raise ValueError('outside bounded CRC-8 family')

    def predict(self, body):
        t, r = table(self.poly), self.init
        for b in body:
            r = t[r ^ b]
        return r ^ self.xorout

    def behavior_key(self):
        # For a fixed polynomial, equality at zero and one zero byte implies
        # equal behavior for all lengths and all contents: T(delta)=delta.
        return self.poly, self.init ^ self.xorout, self.predict(b'\x00')


def samples(codewords):
    by_body = {}
    for i, word in enumerate(codewords):
        if i >= MAX_SAMPLES:
            raise ValueError('sample limit exceeded')
        if not isinstance(word, bytes) or not 2 <= len(word) <= MAX_BODY + 1:
            raise ValueError('expected 1..512 body bytes and a trailing CRC byte')
        b, c = word[:-1], word[-1]
        if b in by_body and by_body[b] != c:
            raise ValueError('contradictory checksums for the same body')
        by_body[b] = c
    return by_body


def fit_train(data):
    """Exploit CRC linearity; equal-length residuals must agree.

    For each surviving polynomial, enumerate only 256 init states; the first
    observed length directly determines xorout. No arbitrary parameter choice.
    """
    if not data:
        return []
    result = []
    for poly in range(1, 256, 2):
        t = table(poly)
        offsets = {}
        for b, c in data.items():
            r = 0
            for x in b:
                r = t[r ^ x]
            diff = r ^ c
            n = len(b)
            if n in offsets and offsets[n] != diff:
                break
            offsets[n] = diff
        else:
            sizes = sorted(offsets)
            states = list(range(256))
            effects, previous = {}, 0
            for n in sizes:
                for _ in range(previous, n):
                    states = [t[x] for x in states]
                effects[n] = states
                previous = n
            first = sizes[0]
            for init in range(256):
                xorout = effects[first][init] ^ offsets[first]
                if all(effects[n][init] ^ xorout == offsets[n] for n in sizes[1:]):
                    result.append(CRCModel(poly, init, xorout))
    return result


def groups(models):
    out = {}
    for m in sorted(set(models)):
        out.setdefault(m.behavior_key(), []).append(m)
    return list(out.values())


def discover(train, validation):
    a, b = samples(train), samples(validation)
    if any(a[k] != b[k] for k in a.keys() & b.keys()):
        raise ValueError('training and validation contradict')
    b = {k: v for k, v in b.items() if k not in a}
    result = dict(status='insufficient_data', models=[], training_candidates=0,
                  train_unique=len(a), validation_unique=len(b), presets=[])
    if len(a) < 6 or len(b) < 4 or len(set(a.values())) < 3 or len(set(b.values())) < 3:
        return result
    result['presets'] = [name for name, fn in CHECKSUMS.items()
                         if all(fn(x) == y for x, y in [*a.items(), *b.items()])]
    candidates = fit_train(a)
    kept = [m for m in candidates if all(m.predict(x) == y for x, y in b.items())]
    count = len(groups(kept))
    result.update(training_candidates=len(candidates), models=kept,
                  status='rejected' if not kept else 'unique_behavior_in_family' if count == 1 else 'ambiguous')
    return result


def plan(models, bodies):
    """Rank supplied prospective bodies by separated behavior-class pairs.

    A body is an offline observation template, never a command to a device.
    """
    reps = [g[0] for g in groups(models)]
    out = []
    for body in dict.fromkeys(bodies):
        if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_BODY:
            raise ValueError('invalid prospective body')
        counts = Counter(m.predict(body) for m in reps)
        n = len(reps)
        pairs = (n*n - sum(v*v for v in counts.values())) // 2
        if pairs:
            out.append(dict(body_hex=body.hex(), separated_pairs=pairs, possible_outputs=len(counts)))
    return sorted(out, key=lambda r: (-r['separated_pairs'], len(r['body_hex']), r['body_hex']))


def refine(models, observations):
    """Only complete observations count; no-response leaves candidates intact."""
    data = samples(observations)
    return [m for m in models if all(m.predict(x) == y for x, y in data.items())]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--train', nargs='+', required=True, help='one complete codeword per file')
    ap.add_argument('--validation', nargs='+', required=True)
    ap.add_argument('--prospective', nargs='*', default=[], help='offline body files without checksum')
    ap.add_argument('--observations', nargs='*', default=[], help='additional independently delimited clean codewords')
    ap.add_argument('--out', default='crc_discovery.json')
    a = ap.parse_args()
    load = lambda paths: [Path(p).read_bytes() for p in paths]
    r = discover(load(a.train), load(a.validation))
    models = r.pop('models')
    r['groups'] = [[asdict(m) for m in g] for g in groups(models)]
    remaining = refine(models, load(a.observations))
    r['remaining_groups'] = [[asdict(m) for m in g] for g in groups(remaining)]
    r['refinement_status'] = ('not_requested' if not a.observations else 'all_conflicted' if not remaining else
                              'conditional_unique_behavior' if len(r['remaining_groups']) == 1 else 'ambiguous')
    r['acquisition_plan'] = plan(remaining, load(a.prospective))
    r['scope'] = 'non-reflected CRC-8 only; whole body; clean delimited frames; no automatic repair'
    Path(a.out).write_text(json.dumps(r, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=r['status'], behavior_groups=len(r['groups']), parameters=len(models), remaining_groups=len(r['remaining_groups']), presets=r['presets']), indent=2))

if __name__ == '__main__':
    main()
