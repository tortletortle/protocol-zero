"""Paired simulation cells; fixed cadence plus out-of-family stress controls."""
import json,random
from collections import Counter
from cadence import infer
from temporal import infer as oracle


def samples(seed,kind,size=1):
    rng=random.Random(seed); a=rng.choice([3,5,7,9,11,13]); b=rng.randrange(256)
    def split(n):
        rows=[]; x=y=0
        pattern=[(rng.randrange(16),rng.randrange(16)) for _ in range(16)] if kind=='lag16' else []
        for t in range(n):
            if kind in ('markov','weak_markov'):
                rate=.12 if kind=='markov' else .7
                x=rng.randrange(16) if t==0 or rng.random()<rate else x
                y=rng.randrange(16) if t==0 or rng.random()<rate else y
            elif kind=='lag16':
                x,y=pattern[t%16]
            elif kind=='cycle':
                x=t%16; y=(t+3)%16
            else:
                x=rng.randrange(16); y=rng.randrange(16)
            if kind=='signal': y=(a*x+b)%256 if rng.random()>=.3 else rng.randrange(256)
            length=rng.randrange(1,9) if kind=='irregular' else size
            rows.extend([bytes((x,y))]*length)
        return rows
    return split(64),split(32),(a,b)


def run(n=40):
    out=[]
    for kind,size in [(k,s) for k in ('null','signal') for s in (1,3,8,16)]+[(k,1) for k in ('markov','weak_markov','irregular','cycle','lag16')]:
        count=Counter(); statuses=Counter()
        for seed in range(n):
            p,q,target=samples(16000+seed,kind,size)
            r=infer(p,q,seed=seed); statuses[r['status']]+=1
            if kind in ('null','signal'):
                count['length_correct']+=r['diagnostic'].get('block_size')==size
            count['auto_hits']+=any((z['kind'],z['a'],z['b'])==('affine',*target) for z in r['edges']) if kind=='signal' else bool(r['edges'])
            if kind in ('null','signal'):
                s=oracle(p,q,size,permutations=199,seed=seed)['edges']
                count['oracle_hits']+=any((z['kind'],z['a'],z['b'])==('affine',*target) for z in s) if kind=='signal' else bool(s)
        out.append(dict(kind=kind,size=size,n=n,**count,statuses=dict(statuses)))
    return out
if __name__=='__main__': print(json.dumps(run(),indent=2))
