"""Held-out conditional permutation tests for byte rules; exchangeable rows only."""
from collections import Counter
import random

def infer(train, validation, alpha=.05, permutations=999, seed=0):
    if len(train)<16 or len(validation)<16: return []
    width=min(map(len,train+validation)); candidates=[]
    for i in range(width):
        for j in range(i+1,width):
            p=[(r[i],r[j]) for r in train]
            if len({x for x,y in p})<8: continue
            best=[]
            for kind,a in [('affine',a) for a in range(1,256)]+[('xor',0)]:
                b,n=Counter((y-a*x)%256 if kind=='affine' else x^y for x,y in p).most_common(1)[0]
                best.append((n,kind,a,b))
            # One training-selected candidate per pair, deterministic ties.
            n,kind,a,b=max(best)
            predicted=[(a*r[i]+b)%256 if kind=='affine' else r[i]^b for r in validation]
            actual=[r[j] for r in validation]
            if min(len(set(predicted)),len(set(actual)))<2: continue
            candidates.append((i,j,kind,a,b,predicted,actual))
    rng=random.Random(seed); out=[]; m=len(candidates)
    for i,j,kind,a,b,pred,actual in candidates:
        hits=sum(x==y for x,y in zip(pred,actual)); shuffled=actual[:]; exceed=0
        for _ in range(permutations):
            rng.shuffle(shuffled); exceed+=sum(x==y for x,y in zip(pred,shuffled))>=hits
        p=(exceed+1)/(permutations+1)
        if p*m<=alpha: out.append((i,j,kind,a,b,hits/len(actual),p,min(1,p*m)))
    return out
