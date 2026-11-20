"""Counter hypotheses over a known field start; no physical semantics assumed."""
def hypotheses(samples, offset=0):
    if len(samples)<2: return []
    out=[]
    for w in (1,2,4):
        if min(map(len,samples))<offset+w: continue
        for e in ('little','big') if w>1 else ('little',):
            v=[int.from_bytes(s[offset:offset+w],e) for s in samples]
            if all((b-a)%(256**w)==1 for a,b in zip(v,v[1:])):out.append((w,e))
    return out

def update(candidates, previous, current, offset=0):
    return [ (w,e) for w,e in candidates if len(current)>=offset+w and (int.from_bytes(current[offset:offset+w],e)-int.from_bytes(previous[offset:offset+w],e))%(256**w)==1 ]
