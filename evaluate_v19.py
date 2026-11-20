"""Independent test stream; checksum-free and out-of-family controls."""
import json,random
from collections import Counter
from pipeline import analyze_pcaps, checksum
from stream_framing import split
from test_stream import packet,pcap


def sample(r,kind):
    frames=[]
    for _ in range(24):
        n=r.randint(5,100)
        body=b'\xa5\x5a'+bytes([n])+r.randbytes(n)
        tail=(checksum(body,kind) if kind in ('SUM8','XOR8','CRC-8/SMBUS') else r.randrange(256))
        frames.append(body+bytes([tail]))
    raw=b''.join(frames)
    if kind=='null': raw=r.randbytes(len(raw))
    start=r.randrange(2**32); chunks=[]; i=0
    while i<len(raw):
        n=r.randint(8,120); chunks.append(packet((start+i)%2**32,raw[i:i+n])); i+=n
    chunks.append(chunks[0]); r.shuffle(chunks)
    return frames,raw,pcap(packet((start-1)%2**32,b'',2),*chunks)


def run(n=30):
    out=[]
    for kind in ('SUM8','XOR8','CRC-8/SMBUS','no_checksum','null'):
        count=Counter()
        for seed in range(n):
            r=random.Random(20000+seed); _,a,p=sample(r,kind); _,b,q=sample(r,kind); truth,test,_=sample(r,kind)
            result=analyze_pcaps([p],[q],502); selected=result['selected']
            count['raw_multiple']+=result['raw_rules']>1
            count['boundary_multiple']+=len(result['groups'])>1
            count['selected_multiple']+=len(selected)>1
            count['any_candidate']+=bool(selected)
            count['checksum_supported']+=any(c['checksums'] for c in selected)
            if kind!='null':
                count['correct_test_candidate']+=any(split(test,rule)==truth for c in selected for rule in c['rules'])
                count['all_test_correct']+=bool(selected) and all(split(test,rule)==truth for c in selected for rule in c['rules'])
                count['true_checksum']+=any(kind in c['checksums'] for c in selected)
        out.append(dict(kind=kind,n=n,**count))
    return out


def aliases(n=40):
    from evaluate_v18 import sample as old_sample
    from stream_reassembly import streams
    count=Counter()
    for seed in range(n):
        r=random.Random(18000+seed); _,p=old_sample(r,'retransmit'); _,q=old_sample(r,'retransmit'); truth,t=old_sample(r,'retransmit')
        raw=next(iter(streams(t,502).values()))['data']; a=analyze_pcaps([p],[q],502)
        count['raw_multiple']+=a['raw_rules']>1
        count['boundary_multiple']+=len(a['groups'])>1
        count['checksum_supported']+=a['status']=='checksum_supported'
        count['all_test_correct']+=bool(a['selected']) and all(split(raw,rule)==truth for group in a['selected'] for rule in group['rules'])
    return dict(kind='v18_aliases',n=n,**count)

if __name__=='__main__': print(json.dumps(run()+[aliases()],indent=2))
