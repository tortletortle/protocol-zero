from collections import Counter
import math

def infer(frames):
    n=min(map(len,frames)); out=[]; i=0
    def constant(j):return len({f[j] for f in frames})==1
    def counter(j,w,endian):
        v=[int.from_bytes(f[j:j+w],endian) for f in frames]; mod=256**w
        return sum((b-a)%mod==1 for a,b in zip(v,v[1:]))/max(1,len(v)-1)
    while i<n-1:
        if constant(i):
            j=i+1
            while j<n-1 and constant(j):j+=1
            out.append((i,j,'constant'));i=j;continue
        if len(set(map(len,frames)))>1 and len({len(f)-f[i] for f in frames})==1:
            out.append((i,i+1,'length'));i+=1;continue
        candidates=[]
        for w in (1,2,4):
            if i+w>n-1:continue
            for e in ('little','big') if w>1 else ('little',):
                if w>1 and any(constant(j) for j in range(i,i+w)):continue
                if counter(i,w,e)>=.95:candidates.append((w,e))
        if candidates:
            w,e=max(candidates);out.append((i,i+w,'counter'+str(w)+e));i+=w;continue
        break
    out.append((i,-1,'unknown'));out.append((-1,0,'checksum_candidate'))
    return out
