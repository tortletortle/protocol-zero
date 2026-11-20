"""Exhaustive bounded CRC-8 maximum-consensus voting; optional NumPy backend."""
from collections import Counter, defaultdict
from functools import lru_cache
from math import ceil
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import numpy as np
from .crc_discovery import CRCModel, table
from . import joint_crc


class BudgetExceeded(Exception):
    pass


@lru_cache(maxsize=128)
def effects(poly):
    """T**n(init) for all initial states and supported covered lengths."""
    t = np.array(table(poly), dtype=np.uint8)
    a = np.empty((522, 256), dtype=np.uint8)
    a[0] = np.arange(256, dtype=np.uint8)
    for n in range(1, len(a)):
        a[n] = t[a[n-1]]
    a.flags.writeable = False
    return a


class ConsensusSolver:
    def __init__(self, max_votes=400_000_000):
        if max_votes <= 0:
            raise ValueError('positive vote budget required')
        self.max_votes = max_votes
        self.votes = 0
        self.calls = 0
        self.pruned = 0

    def __call__(self, words, rate):
        if not .5 < rate <= 1:
            raise ValueError('unsupported consensus threshold')
        words = sorted(set(words))
        if not words:
            return []
        if any(not 1 <= len(b) <= 521 or not 0 <= c < 256 for b,c in words):
            raise ValueError('outside covered length or CRC range')
        self.calls += 1
        k = ceil(rate * len(words))
        lengths = np.array([len(b) for b,c in words])
        by_length = defaultdict(list)
        for i,n in enumerate(lengths):
            by_length[int(n)].append(i)
        # Each init implies one xorout per observation. Count every pair exactly.
        offsets = (np.arange(256,dtype=np.int32)*256)[None,:]
        result = {}
        for poly in range(1,256,2):
            t = table(poly)
            residuals = []
            for b,c in words:
                v = 0
                for x in b:
                    v = t[v^x]
                residuals.append(v^c)
            # Necessary upper bound: one residual per length can be inliers.
            if sum(max(Counter(residuals[i] for i in ids).values()) for ids in by_length.values()) < k:
                self.pruned += 1
                continue
            cost = 256 * len(words)
            if self.votes + cost > self.max_votes:
                raise BudgetExceeded
            self.votes += cost
            res = np.array(residuals,dtype=np.uint8)[:,None]
            ids = (effects(poly)[lengths] ^ res) + offsets
            counts = np.bincount(ids.ravel(),minlength=65536)
            for idx in np.flatnonzero(counts >= k):
                init,xorout = divmod(int(idx),256)
                m = CRCModel(poly,init,xorout)
                result.setdefault(m.behavior_key(),[]).append(m)
        return list(result.values())


def infer(train, validation, *, rate=.65, max_votes=400_000_000, **kwargs):
    solver = ConsensusSolver(max_votes)
    try:
        r = joint_crc.infer(train,validation,rate=rate,solver=solver,**kwargs)
    except BudgetExceeded:
        r = dict(status='budget_exceeded',models=[],passing=None)
    r['search'] = dict(votes=solver.votes,budget=max_votes,solver_calls=solver.calls,
                       pruned_polynomials=solver.pruned,complete=r['status']!='budget_exceeded')
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('train','validation','test'):
        p.add_argument('--'+name,nargs='+',required=True)
    p.add_argument('--out',default='robust_crc.json')
    p.add_argument('--max-votes',type=int,default=400_000_000)
    a=p.parse_args(); load=lambda paths:[Path(x).read_bytes() for x in paths]
    r=infer(load(a.train),load(a.validation),max_votes=a.max_votes); models=r.pop('models')
    r['decoded']=[joint_crc.decode(s,models) for s in load(a.test)]
    r['models']=[dict(layout=l.report(),crc_parameters=[asdict(m) for m in ms]) for l,ms in models]
    Path(a.out).write_text(json.dumps(r,indent=2),encoding='utf8')
    print(r['status'],len(models),r['search'])

if __name__=='__main__':main()
