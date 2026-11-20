"""Finite-observation equivalence and length-only acquisition planning.

No active device commands, no automatic repair and no claim of semantic truth.
"""
from __future__ import annotations
from collections import defaultdict
from itertools import combinations
from dataclasses import asdict
import argparse
import json
from pathlib import Path
from .framing import rank_hypotheses, decode_stream
from .model import FrameModel
from .checksums import checksum


def _signature(h):
    return tuple(tuple((sid, r.start, r.end) for sid, r in h[i]['records']) for i in (2, 3))


def fit_models(train, validation, *, score_window=0.15, **gates):
    """Keep all passing models in a top-scoring *observed* boundary group.

    Competing near-top groups also remain active. Lower groups remain visible.
    The score window is a heuristic, not a probability or completeness proof.
    """
    if score_window < 0:
        raise ValueError('score_window must be nonnegative')
    ranked = rank_hypotheses(train, validation, **gates)
    groups = defaultdict(list)
    for h in ranked:
        groups[_signature(h)].append(h)
    if not ranked:
        return dict(status='rejected' if train and validation else 'insufficient_data', models=[], groups=[])
    best = ranked[0][0]
    active, report = [], []
    for signature, members in groups.items():
        selected = best - members[0][0] <= score_window
        if selected:
            active.extend(h[1] for h in members)
        report.append(dict(active=selected, score=members[0][0],
                           train_spans=len(signature[0]), validation_spans=len(signature[1]),
                           candidates=[dict(model=h[1].to_dict(), score=h[0]) for h in members]))
    count = sum(g['active'] for g in report)
    status = ('unique_candidate' if len(active)==1 else 'observationally_equivalent'
              if count==1 else 'competing_parses')
    return dict(status=status, models=active, groups=report)


def consensus(data, models, stream_id=0):
    """Only report spans on which every active model agrees, never repair bytes."""
    models = tuple(dict.fromkeys(models))
    spans = defaultdict(list)
    for i, m in enumerate(models):
        for rec in decode_stream(data, m, stream_id)['frames']:
            spans[rec.start, rec.end].append(i)
    agreed, contested = [], []
    for (a, b), votes in sorted(spans.items()):
        row = dict(start=a, end=b, data_hex=data[a:b].hex(), voters=votes,
                   model_count=len(models), verified_ground_truth=False)
        (agreed if len(votes)==len(models) else contested).append(row)
    return dict(stream_id=stream_id, agreed=agreed, contested=contested)


def constraints(model, total_size):
    """Required header bytes for an independently bounded total frame length.

    None means impossible under this bounded model, not impossible on hardware.
    Unspecified bytes are wildcards, never assumed constant.
    """
    n = total_size-model.payload_offset-model.trailer_size
    if not 0 <= n <= min(model.max_payload, (1 << (8*model.length_width))-1):
        return None
    fixed = dict(enumerate(model.sync))
    for i, value in enumerate(n.to_bytes(model.length_width, model.length_endian), model.length_offset):
        if i in fixed and fixed[i] != value:
            return None
        fixed[i] = value
    return fixed


def plan_lengths(models, allowed_total_sizes):
    """Rank user-approved capture sizes by separated candidate pairs.

    A one-sided test only distinguishes if a complete frame is actually observed;
    silence is never evidence. Checksum-only distinctions are not modeled.
    """
    models = tuple(dict.fromkeys(models))
    out = []
    for size in sorted(set(allowed_total_sizes)):
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError('capture sizes must be positive integers')
        req = [constraints(m, size) for m in models]
        two, one = [], []
        for i, j in combinations(range(len(models)), 2):
            a, b = req[i], req[j]
            if (a is None) != (b is None):
                one.append((i, j))
            elif a is not None and b is not None and any(a[k]!=b[k] for k in a.keys() & b.keys()):
                two.append((i,j))
        if two or one:
            out.append(dict(total_size=size, two_sided=two, one_sided=one,
                            feasible_models=[i for i, c in enumerate(req) if c is not None],
                            score=2*len(two)+len(one), conditional_on_complete_frame=True))
    return sorted(out, key=lambda r:(-r['score'], -len(r['two_sided']), r['total_size']))


def _matches(frame, model):
    req = constraints(model, len(frame))
    return (req is not None and all(i<len(frame) and frame[i]==v for i,v in req.items())
            and int.from_bytes(frame[-model.trailer_size:], 'big')==checksum(frame[:-model.trailer_size], model.checksum))


def refine(models, complete_frames, *, min_confirmations=3):
    """Conservative conflict gate for independently delimited, clean observations.

    Exact duplicate frames do not count twice. Absence of a frame never eliminates
    candidates. Retain partially contradicted models until the conflict threshold.
    """
    if min_confirmations < 2:
        raise ValueError('at least two distinct observations required')
    models = tuple(dict.fromkeys(models))
    observations = tuple(dict.fromkeys(bytes(f) for f in complete_frames if f))
    rows, kept = [], []
    for i, m in enumerate(models):
        matches = sum(_matches(f, m) for f in observations)
        conflicts = len(observations)-matches
        retained = conflicts < min_confirmations
        if retained:
            kept.append(m)
        rows.append(dict(index=i, matches=matches, conflicts=conflicts, retained=retained))
    if not models:
        status = 'no_initial_models'
    elif len(observations)<min_confirmations:
        status = 'insufficient_observations'
    elif not kept:
        status = 'all_conflicted'
    elif len(kept)==1 and any(r['retained'] and r['matches']>=min_confirmations and r['conflicts']==0 for r in rows):
        status = 'unique_under_observations'
    elif len(kept)<len(models):
        status = 'narrowed'
    else:
        status = 'unresolved'
    return dict(status=status, models=kept, observations=len(observations), evidence=rows)


def analyze_equivalence(train, validation, test, *, allowed_total_sizes=(), complete_frames=()):
    fit = fit_models(train, validation)
    initial = fit['models']
    refinement = refine(initial, complete_frames)
    current = refinement['models']
    return dict(status=fit['status'], initial_models=[m.to_dict() for m in initial],
                groups=fit['groups'], refinement={**refinement,'models':[m.to_dict() for m in current]},
                current_models=[m.to_dict() for m in current],
                decoded=[consensus(s,current,i) for i,s in enumerate(test)],
                acquisition_plan=plan_lengths(current,allowed_total_sizes),
                limitations=['bounded family and finite observations', 'scores are not probabilities',
                             'complete-frame observations must be independently delimited and clean',
                             'no-response is not evidence', 'no automatic device commands or repairs'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ('train','validation','test'):
        ap.add_argument('--'+arg,nargs='+',required=True)
    ap.add_argument('--allowed-frame-sizes',nargs='*',type=int,default=[])
    ap.add_argument('--complete-frames',nargs='*',default=[],help='independently delimited clean frame files (one frame per file)')
    ap.add_argument('--out',default='equivalence_result.json')
    a=ap.parse_args()
    load=lambda xs:[Path(p).read_bytes() for p in xs]
    result=analyze_equivalence(load(a.train),load(a.validation),load(a.test),allowed_total_sizes=a.allowed_frame_sizes,complete_frames=load(a.complete_frames))
    Path(a.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],candidates=len(result['current_models']),agreed=sum(len(d['agreed']) for d in result['decoded']),planned=result['acquisition_plan'][:3]),indent=2))

if __name__=='__main__':
    main()
