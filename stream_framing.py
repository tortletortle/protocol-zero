"""Search length-based grammars on complete, start-aligned byte streams."""


def split(data,rule,max_frame=4096):
    offset,width,endian,bias=rule; p=0; out=[]
    while p<len(data):
        end=p+offset+width
        if end>len(data): return None
        n=int.from_bytes(data[p+offset:end],endian)+bias
        if not offset+width<=n<=max_frame or p+n>len(data): return None
        out.append(data[p:p+n]); p+=n
    return out


def infer(train,validation,max_offset=8,bias_limit=16):
    if not train or not validation or not all(train+validation): return []
    out=[]
    for o in range(max_offset):
        for w in (1,2,4):
            for e in ('big','little') if w>1 else ('big',):
                for b in range(-bias_limit,bias_limit+1):
                    rule=(o,w,e,b)
                    a=[split(d,rule) for d in train]
                    if any(x is None for x in a): continue
                    lengths=[len(f) for stream in a for f in stream]
                    if len(lengths)<8 or len(set(lengths))<3: continue
                    c=[split(d,rule) for d in validation]
                    if any(x is None for x in c): continue
                    lengths=[len(f) for stream in c for f in stream]
                    if len(lengths)>=8 and len(set(lengths))>=3: out.append(rule)
    return out
