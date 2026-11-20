"""Controlled fault injection; independent streams per train/test, no live capture."""
import json, random
from collections import Counter
from test_stream import packet,pcap
from capture import payloads
from stream_reassembly import streams
from stream_framing import infer,split

RULE=(4,2,'big',6)


def sample(r,mode):
    frames=[]
    for i in range(24):
        n=r.randint(8,400)
        frames.append(r.randbytes(2)+bytes(2)+(n+2).to_bytes(2,'big')+bytes([1,3])+r.randbytes(n))
    raw=b''.join(frames); start=r.randrange(2**32)
    if mode=='aligned': parts=list(enumerate(frames)); parts=[(sum(map(len,frames[:i])),b) for i,b in parts]
    else:
        cuts=[0]
        while cuts[-1]<len(raw): cuts.append(min(len(raw),cuts[-1]+r.randint(30,650)))
        parts=[(i,raw[i:j]) for i,j in zip(cuts,cuts[1:])]
        if mode=='gap': del parts[len(parts)//2]
        if mode=='conflict':
            i,b=parts[len(parts)//2]; parts.append((i,bytes([b[0]^1])+b[1:]))
        if mode in ('retransmit','wrap'):
            i,b=parts[len(parts)//2]; parts.extend([(i,b),(i+3,b[3:])]); r.shuffle(parts)
        if mode=='wrap': start=2**32-20
    cap=pcap(packet((start-1)%2**32,b'',2),*(packet((start+i)%2**32,b) for i,b in parts))
    return frames,cap


def run(n=40):
    rows=[]
    for mode in ('aligned','segmented','retransmit','wrap','gap','conflict'):
        c=Counter()
        for seed in range(n):
            r=random.Random(18000+seed); f,p=sample(r,mode); g,q=sample(r,mode)
            old=list(payloads(q,502)); c['packet_exact']+=old==g
            a=next(iter(streams(p,502).values())); b=next(iter(streams(q,502).values()))
            c['both_reassembled']+=a['status']==b['status']=='ok' and a['data']==b''.join(f) and b['data']==b''.join(g)
            if mode in ('gap','conflict'):
                c['correct_reject']+=a['status']==b['status']==mode
            if a['status']==b['status']=='ok':
                rules=infer([a['data']],[b['data']]); c['true_rule']+=RULE in rules
                c['unique_rule']+=rules==[RULE]; c['ambiguous']+=len(rules)>1
                c['true_boundaries']+=RULE in rules and split(b['data'],RULE)==g
        rows.append(dict(mode=mode,n=n,**c))
    # Out-of-family negative: unrelated uniformly random byte streams.
    c=Counter()
    for seed in range(n):
        r=random.Random(19000+seed); rules=infer([r.randbytes(2000)],[r.randbytes(2000)])
        c['any_rule']+=bool(rules)
    rows.append(dict(mode='random_null',n=n,**c))
    return rows

if __name__=='__main__': print(json.dumps(run(),indent=2))
