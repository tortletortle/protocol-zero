"""Carry evidence ranks competing interpretations; does not establish semantics."""
from ambiguity import hypotheses

def infer(samples, offset=0):
    candidates=hypotheses(samples,offset)
    result=[]
    for w,e in candidates:
        edges=[]
        for k in range(1,w):
            low=offset if e=='little' else offset+w-k
            high=offset+k if e=='little' else low-1
            mask=256**k-1
            opportunities=matches=violations=0
            for a,b in zip(samples,samples[1:]):
                carry=int.from_bytes(a[low:low+k],e)==mask
                delta=(b[high]-a[high])%256
                opportunities+=carry; matches+=carry and delta==1; violations+=delta!=int(carry)
            edges.append(dict(level=k,opportunities=opportunities,matches=matches,violations=violations))
        result.append(dict(width=w,endian=e,edges=edges,score=sum(x['matches'] for x in edges)))
    # Shorter hypotheses remain possible even if a carry is observed.
    return sorted(result,key=lambda x:(-x['score'],x['width'],x['endian']))
