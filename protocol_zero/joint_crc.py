"""Joint bounded framing/CRC-8 inference from raw streams; offline only."""
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
import argparse
import json
from .crc_discovery import CRCModel, table
from .framing import _sync_candidates, _positions, _Candidate, _select

MAX_BYTES = 65536
MAX_MODELS = 4096

@dataclass(frozen=True)
class Layout:
    sync: bytes
    offset: int
    width: int
    endian: str
    payload_offset: int
    suffix: int
    coverage_start: int

    def scan(self, stream):
        for a in _positions(stream, self.sync):
            lo, hi = a+self.offset, a+self.offset+self.width
            if hi > len(stream):
                continue
            n = int.from_bytes(stream[lo:hi], self.endian)
            b = a+self.payload_offset+n+1+self.suffix
            if n <= 512 and b <= len(stream):
                c = b-1-self.suffix
                yield a, b, stream[a+self.coverage_start:c], stream[c]

    def report(self):
        return {**asdict(self), 'sync':self.sync.hex()}


def _raw(streams, layout):
    return tuple(tuple((sid,a,b,body,c) for a,b,body,c in layout.scan(s))
                 for sid,s in enumerate(streams))


def _words(raw):
    return set((body,c) for rows in raw for _,_,_,body,c in rows)


@lru_cache(maxsize=128)
def _basis(poly):
    """Eight columns of T**n, where T advances the CRC state by one zero byte."""
    t=table(poly); rows=[tuple(1<<i for i in range(8))]
    for _ in range(521):
        rows.append(tuple(t[x] for x in rows[-1]))
    return rows


def _fit_exact(words):
    """No repeated-length anchor: eliminate xorout, solve eight GF(2) variables.

    Exact fallback only; inconsistent input is rejected, not corrected.
    """
    rows=sorted(words,key=lambda w:(len(w[0]),w)); reps={}
    for poly in range(1,256,2):
        t=table(poly); basis=_basis(poly); offsets={}; pivots={}; good=True
        for body,c in rows:
            n=len(body); r=0
            for x in body:r=t[r^x]
            v=r^c
            if n in offsets:
                if offsets[n]!=v:good=False;break
                continue
            if not offsets:
                first=n; initial=v
            else:
                cols=[a^b for a,b in zip(basis[n],basis[first])]; target=v^initial
                for bit in range(8):
                    eq=sum(((col>>bit)&1)<<j for j,col in enumerate(cols))|(((target>>bit)&1)<<8)
                    while eq&255:
                        k=(eq&255).bit_length()-1
                        if k not in pivots:pivots[k]=eq;break
                        eq^=pivots[k]
                    else:
                        if eq:good=False;break
                if not good:break
            offsets[n]=v
        if not good:continue
        for init in range(256):
            if any(((eq&init).bit_count()&1)!=(eq>>8) for eq in pivots.values()):continue
            r=0
            for j,col in enumerate(basis[first]):
                if init&(1<<j):r^=col
            m=CRCModel(poly,init,r^initial)
            reps.setdefault(m.behavior_key(),[]).append(m)
    return list(reps.values())


def _fit(words, rate):
    """Anchor on a repeated length; count distinct codewords, not duplicates."""
    by_len = defaultdict(list)
    for body,c in sorted(words):
        by_len[len(body)].append((body,c))
    anchor = max(by_len, key=lambda n: (len({b for b,c in by_len[n]}), -n))
    anchor_words = by_len[anchor]
    if len({b for b,c in anchor_words}) < 4:
        return _fit_exact(words)
    reps = {}
    for poly in range(1,256,2):
        t = table(poly)
        def residual(b,c):
            r = 0
            for x in b:
                r = t[r ^ x]
            return r ^ c
        hist = Counter(residual(b,c) for b,c in anchor_words)
        # Any surviving model must satisfy the anchor gate, not just its mode.
        offsets = [v for v,k in hist.items() if k >= rate*len(anchor_words)]
        if not offsets:
            continue
        counts = {n: Counter(residual(b,c) for b,c in rows) for n,rows in by_len.items()}
        states = list(range(256)); effects = {}; previous = 0
        for n in sorted(counts):
            for _ in range(previous,n):
                states = [t[x] for x in states]
            effects[n] = states; previous = n
        for init in range(256):
            for v in offsets:
                xor = effects[anchor][init]^v
                support = sum(h[effects[n][init]^xor] for n,h in counts.items())
                if support >= rate*len(words):
                    m = CRCModel(poly,init,xor)
                    reps.setdefault(m.behavior_key(),[]).append(m)
    return list(reps.values())


def _stats(raw, model, total):
    count=0; spans=[]; bodies=set(); matched=0
    for rows in raw:
        ok=[]
        for sid,a,b,body,c in rows:
            if model.predict(body)==c:
                ok.append(_Candidate(a,b,body,True,10.0)); matched+=1
        chosen=_select(ok)
        if rows:
            spans.extend((rows[0][0],r.start,r.end) for r in chosen)
        count+=len(chosen); bodies.update(r.data for r in chosen)
    coverage=sum(b-a for _,a,b in spans)/max(total,1)
    rate=matched/max(sum(map(len,raw)),1)
    return count,coverage,rate,tuple(spans),bodies


def infer(train, validation, *, rate=.65, sync_limit=6, score_window=.15, solver=None):
    if not .5 < rate <= 1 or not 1 <= sync_limit <= 8 or score_window < 0:
        raise ValueError('invalid search thresholds')
    if not train or not validation:
        return {'status':'insufficient_data','models':[],'passing':0}
    if sum(map(len,train+validation)) > MAX_BYTES:
        return {'status':'budget_exceeded','models':[],'passing':0}
    nt,nv=sum(map(len,train)),sum(map(len,validation))
    passing=[]; scanned=0
    @lru_cache(maxsize=256)
    def solve(words):
        return (solver or _fit)(words,rate)
    for sync in _sync_candidates(train,sync_limit):
        for offset in range(2,6):
            for width,endian in ((1,'little'),(2,'little'),(2,'big')):
                for extra in range(3):
                    for suffix in (0,1):
                        for start in (0,2):
                            l=Layout(sync,offset,width,endian,offset+width+extra,suffix,start)
                            a,b=_raw(train,l),_raw(validation,l); scanned+=1
                            wa,wb=_words(a),_words(b)
                            if len({x for x,c in wa})<8 or len({x for x,c in wb})<6:
                                continue
                            for params in solve(frozenset(wa)):
                                m=params[0]
                                ta=_stats(a,m,nt)
                                if ta[0]<8 or ta[1]<.35 or ta[2]<rate or len(ta[4])<8:
                                    continue
                                vb=_stats(b,m,nv)
                                # Training overlap cannot supply validation support.
                                novel=vb[4]-{x for x,c in wa}
                                if vb[0]<6 or vb[1]<.35 or vb[2]<rate or len(novel)<6:
                                    continue
                                score=2*vb[0]+4*vb[1]+3*vb[2]+.02*ta[0]
                                passing.append((score,l,params,ta[3],vb[3]))
                                if len(passing)>MAX_MODELS:
                                    return {'status':'budget_exceeded','models':[],'passing':len(passing),'layouts':scanned}
    if not passing:
        return {'status':'rejected','models':[],'passing':0,'layouts':scanned}
    passing.sort(key=lambda row:-row[0]); top=passing[0][0]
    def signature(row):
        # An unchecked suffix cannot earn evidence just by covering more bytes.
        return tuple(tuple((sid,a,b-row[1].suffix) for sid,a,b in spans) for spans in row[3:5])
    signatures={signature(r) for r in passing if top-r[0]<=score_window}
    active=[r for r in passing if signature(r) in signatures]
    return {'status':'unique_candidate' if len(active)==1 else 'ambiguous',
            'models':[(l,p) for _,l,p,_,_ in active], 'passing':len(passing),'layouts':scanned}


def decode(stream, models):
    """Unanimity over active layout/CRC behavior groups, not ground truth."""
    votes=Counter()
    for layout,params in models:
        m=params[0]
        frames=_select([_Candidate(a,b,body,True,10.) for a,b,body,c in layout.scan(stream) if m.predict(body)==c])
        votes.update((r.start,r.end) for r in frames)
    return {'agreed':[(a,b) for (a,b),n in sorted(votes.items()) if n==len(models)],
            'contested':[(a,b,n) for (a,b),n in sorted(votes.items()) if n!=len(models)]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('train','validation','test'):
        p.add_argument('--'+name,nargs='+',required=True)
    p.add_argument('--out',default='joint_crc.json'); a=p.parse_args()
    load=lambda paths:[Path(x).read_bytes() for x in paths]
    r=infer(load(a.train),load(a.validation)); models=r.pop('models')
    r['decoded']=[decode(s,models) for s in load(a.test)]
    r['models']=[{'layout':l.report(),'crc_parameters':[asdict(m) for m in ms]} for l,ms in models]
    r['scope']='bounded non-reflected CRC-8; no repairs; unanimous spans are hypotheses'
    Path(a.out).write_text(json.dumps(r,indent=2)); print(r['status'],len(models))

if __name__=='__main__': main()
