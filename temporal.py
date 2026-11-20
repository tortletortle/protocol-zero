"""Block permutation inference, valid only for independently exchangeable blocks."""
from collections import Counter
import random


def infer(train, validation, block_size, alpha=.05, permutations=999, seed=0):
    """Select on training only; preserve within-block order in validation.

    Caller must supply a justified block size and independent train/validation.
    Never interprets significance as causality or a unique field encoding.
    """
    if not isinstance(block_size, int) or block_size < 1:
        raise ValueError('positive integer block_size required')
    if not 0 < alpha < 1 or permutations < 1:
        raise ValueError('invalid test settings')
    if len(validation) % block_size:
        raise ValueError('validation must contain complete blocks')
    blocks = len(validation)//block_size
    if len(train)<16 or blocks<8:
        return dict(status='insufficient_blocks', tested=0, edges=[])
    width=min(map(len,train+validation)); candidates=[]
    for i in range(width):
        for j in range(i+1,width):
            pairs=[(r[i],r[j]) for r in train]
            if len({x for x,y in pairs})<8: continue
            best=[]
            for kind,a in [('affine',a) for a in range(1,256)]+[('xor',0)]:
                b,n=Counter((y-a*x)%256 if kind=='affine' else x^y for x,y in pairs).most_common(1)[0]
                best.append((n,kind,a,b))
            n,kind,a,b=max(best)
            pred=[(a*r[i]+b)%256 if kind=='affine' else r[i]^b for r in validation]
            actual=[r[j] for r in validation]
            candidates.append((i,j,kind,a,b,pred,actual))
    m=len(candidates)
    if m/(permutations+1)>alpha:
        return dict(status='insufficient_permutations',tested=m,edges=[])
    rng=random.Random(seed); edges=[]
    for i,j,kind,a,b,pred,actual in candidates:
        if min(len(set(pred)),len(set(actual)))<2: continue
        # Precompute every cross-block agreement count.
        matrix=[[sum(pred[u*block_size+k]==actual[v*block_size+k] for k in range(block_size))
                 for v in range(blocks)] for u in range(blocks)]
        hits=sum(matrix[u][u] for u in range(blocks)); order=list(range(blocks)); exceed=0
        for _ in range(permutations):
            rng.shuffle(order)
            exceed+=sum(matrix[u][v] for u,v in enumerate(order))>=hits
        p=(exceed+1)/(permutations+1)
        if p*m<=alpha:
            edges.append(dict(i=i,j=j,kind=kind,a=a,b=b,agreement=hits/len(actual),p=p,adjusted_p=min(1,p*m)))
    return dict(status='ok',tested=m,edges=edges)
