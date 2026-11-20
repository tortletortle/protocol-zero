"""Exploratory stress: broadly random lengths and corruption/deletion."""
import csv,random,statistics
from pathlib import Path
from joint_crc_benchmark import setup,independent,f1
from protocol_zero.joint_crc import infer,decode


def capture(l,m,seed,count,kind):
    r=random.Random(seed);out=bytearray(r.randbytes(7));truth=set()
    for i in range(count):
        size=r.randrange(4,65)
        if kind=='bursty_deletion':size=r.choice([8,13,22,31])
        p=r.randbytes(size);body=l.sync+bytes([i%256,size])+p
        q=bytearray(body+bytes([independent(body,m)]));good=True
        if kind=='sparse_noise' and i%7==3:q[-2]^=1;good=False
        if kind=='bursty_deletion' and i%11 in (2,3):del q[r.randrange(4,len(q)-1)];good=False
        a=len(out);out.extend(q)
        if good:truth.add((a,len(out)))
        out.extend(r.randbytes(r.randrange(0,6)))
    return bytes(out),truth


def run():
    rows=[]
    for kind in ('random_clean','sparse_noise','bursty_deletion'):
        for seed in range(82600,82612):
            l,m=setup(seed,'unknown');a,_=capture(l,m,seed+10000,60,kind);b,_=capture(l,m,seed+20000,40,kind);c,t=capture(l,m,seed+30000,50,kind)
            fit=infer([a],[b]);d=decode(c,fit['models']);p=set(d['agreed']);allp=p|{(x,y) for x,y,_ in d['contested']}
            rows.append(dict(kind=kind,seed=seed,status=fit['status'],accepted=bool(fit['models']),truth_retained=any(q==l and m in ms for q,ms in fit['models']),f1=f1(p,t),possible_recall=len(allp&t)/len(t),false_agreed=len(p-t)))
        s=[r for r in rows if r['kind']==kind];print(kind,sum(r['accepted'] for r in s),sum(r['truth_retained'] for r in s),statistics.mean(r['f1'] for r in s),sum(r['false_agreed'] for r in s))
    with (Path(__file__).parent/'v024_stress.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

if __name__=='__main__':run()
