"""Exact byte relations with held-out verification; not semantic inference."""

def infer(train, validation):
    if len(train)<4 or len(validation)<4: return []
    width=min(map(len,train+validation)); out=[]
    for i in range(width):
        for j in range(i+1,width):
            pairs=[(r[i],r[j]) for r in train]; check=[(r[i],r[j]) for r in validation]
            if min(len(set(x for x,y in pairs)),len(set(x for x,y in check)))<4: continue
            x0,y0=pairs[0]
            for a in range(256):
                b=(y0-a*x0)%256
                if a and all((a*x+b)%256==y for x,y in pairs+check): out.append((i,j,'affine',a,b))
            k=x0^y0
            if all(x^k==y for x,y in pairs+check): out.append((i,j,'xor',k))
    return out

def counters(train, validation):
    if len(train)<4 or len(validation)<4: return []
    out=[]
    for i in range(min(map(len,train+validation))):
        for w in (1,2,4):
            if i+w>min(map(len,train+validation)): continue
            for e in ('little','big') if w>1 else ('little',):
                m=256**w
                def deltas(rows):
                    v=[int.from_bytes(r[i:i+w],e) for r in rows]
                    return [(b-a)%m for a,b in zip(v,v[1:])]
                d=deltas(train); s=d[0]
                if s and all(x==s for x in d+deltas(validation)): out.append((i,w,e,s))
    return out
