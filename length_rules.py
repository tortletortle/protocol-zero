"""Enumerate length candidates from externally delimited, variable-size records."""


def infer(train, validation, max_offset=16):
    if min(len(train),len(validation))<8 or min(len(set(map(len,train))),len(set(map(len,validation))))<3:
        return {'status':'insufficient_variation','rules':[]}
    width=min(map(len,train+validation)); rules=[]
    for offset in range(min(max_offset,width)):
        for size in (1,2,4):
            if offset+size>width: continue
            for endian in ('big','little') if size>1 else ('big',):
                def residuals(rows):
                    return {len(r)-int.from_bytes(r[offset:offset+size],endian) for r in rows}
                bias=residuals(train)
                if len(bias)==1 and bias==residuals(validation):
                    b=next(iter(bias))
                    if abs(b)<=256: rules.append(dict(offset=offset,width=size,endian=endian,bias=b))
    return {'status':'ok' if rules else 'no_rule','rules':rules}
