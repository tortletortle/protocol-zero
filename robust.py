"""Robust byte relation candidates and compatibility graph; no causal claims."""
from collections import Counter

def infer(train, validation, threshold=.8):
    if len(train)<16 or len(validation)<16: return []
    width=min(map(len,train+validation)); out=[]
    for i in range(width):
        for j in range(i+1,width):
            p=[(r[i],r[j]) for r in train]; q=[(r[i],r[j]) for r in validation]
            if min(len({x for x,y in p}),len({x for x,y in q}))<8: continue
            for kind,a in [('affine',a) for a in range(1,256)]+[('xor',0)]:
                residual=lambda x,y: (y-a*x)%256 if kind=='affine' else x^y
                for b,n in Counter(residual(x,y) for x,y in p).items():
                    if n/len(p)<threshold: continue
                    v=sum(residual(x,y)==b for x,y in q)/len(q)
                    if v>=threshold: out.append((i,j,kind,a,b,n/len(p),v))
    return sorted(out,key=lambda z:-min(z[-2:]))

def graph(candidates):
    """Group competing explanations per pair without pretending they are exclusive."""
    edges={}
    for i,j,*rule in candidates: edges.setdefault((i,j),[]).append(rule)
    return edges
