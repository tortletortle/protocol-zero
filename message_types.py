"""Passive candidate type bytes; predictive association is not semantic proof."""
from collections import Counter, defaultdict
from math import log2


def project(sessions, offset):
    return [[(d, f[offset]) for d, f in s] for s in sessions]


def gain(train, validation, depth=2):
    base=defaultdict(Counter); ctx=defaultdict(Counter)
    def events(s):
        for i,(d,v) in enumerate(s): yield d,v,tuple(s[max(0,i-depth):i])
    for s in train:
        for d,v,h in events(s): base[d][v]+=1; ctx[d,h][v]+=1
    score=0.; n=0
    for s in validation:
        for d,v,h in events(s):
            if v not in base[d]: return None
            k=len(base[d]); b=base[d]; c=ctx[d,h]
            pb=(b[v]+1)/(sum(b.values())+k)
            pc=(c[v]+1)/(sum(c.values())+k)
            score+=log2(pc/pb); n+=1
    return score/n if n else None


def infer(train, validation, max_offset=16, threshold=.2):
    if not train or not validation or any(not s for s in train+validation): return []
    width=min(len(f) for s in train+validation for _,f in s); out=[]
    for o in range(min(width,max_offset)):
        a,b=project(train,o),project(validation,o)
        values=defaultdict(set)
        for s in a:
            for d,v in s: values[d].add(v)
        if not any(len(v)>1 for v in values.values()) or any(len(v)>16 for v in values.values()): continue
        varying=sum(any(len({v for d,v in s if d==direction})>1 for direction in values) for s in a)
        if varying*2<len(a): continue
        g=gain(a,b)
        if g is not None and g>=threshold: out.append(dict(offset=o,gain_bits=g))
    return sorted(out,key=lambda c:(-c['gain_bits'],c['offset']))


def events(s,offset):
    return ['%s:%02x'%(d,f[offset]) for d,f in s]
