"""Held-out serialized-parser benchmark, independently generated CRC-8/SMBUS."""
import json,random
from collections import Counter
from pipeline import analyze
from protocol_spec import export,load,decode


def crc_reference(body):
    v=int.from_bytes(body,'big')<<8
    for k in range(len(body)*8-1,-1,-1):
        if v & (1<<(k+8)): v^=0x107<<k
    return v


def sample(r,kind):
    rows=[]
    for _ in range(24):
        n=r.randint(5,100); body=bytes([165,90,n])+r.randbytes(n)
        tail={'SUM8':lambda:sum(body)&255,'CRC':lambda:crc_reference(body),'none':lambda:r.randrange(256)}[kind]()
        rows.append(body+bytes([tail]))
    return rows


def run(n=40):
    results=[]
    for kind in ('SUM8','CRC','none'):
        c=Counter()
        for seed in range(n):
            r=random.Random(21000+seed); a,b,t=[sample(r,kind) for _ in range(3)]
            spec=load(json.dumps(export(analyze([b''.join(a)],[b''.join(b)]))))
            raw=b''.join(t); expected=[f.hex() for f in t]
            normal=decode(spec,raw)
            c['correct_unique_boundaries']+=len(normal['alternatives'])==1 and normal['alternatives'][0]['frames']==expected
            c['verified']+=normal['status']=='checksum_verified'
            c['unverified']+=normal['status']=='unverified'
            damaged=bytearray(raw); damaged[3]^=1
            c['corruption_rejected']+=not decode(spec,bytes(damaged))['alternatives']
            c['truncation_rejected']+=not decode(spec,raw[:-1])['alternatives']
        results.append(dict(kind=kind,n=n,**c))
    return results

if __name__=='__main__': print(json.dumps(run(),indent=2))
