import random,json,statistics,shutil
from collections import Counter
from benchmark import edges,select
from joint import fit,predict
from calibration import evidence

def crc(data,poly,init=0):
    v=init
    for x in data:
        v ^= x
        for _ in range(8): v=((v<<1)^(poly if v&128 else 0))&255
    return v
MODELS={'CRC-8/SMBUS':(7,0,0),'CRC-8/SAE-J1850':(29,255,255),'CRC-8/AUTOSAR':(47,255,255)}
def check(q,k):
    p,i,x=MODELS[k];return crc(q,p,i)^x

def generate(seed,kind):
    r=random.Random(seed);h=r.randbytes(2);d=bytearray(r.randbytes(3));truth=[]
    for _ in range(75):
        p=r.randbytes(r.randrange(5,21));q=h+bytes([len(p)])+p
        c=check(q,kind) if kind in MODELS else (sum(x*x for x in q)+17)%256
        start=len(d);d.extend(q+bytes([c]));truth.append((start,len(d)))
        if r.random()<.2:d.extend(r.randbytes(3))
    return bytes(d),truth

def frames(d,m):
    h,k=m;return select([(i,j) for i,j in edges(d,h,2,4) if check(d[i:j-1],k)==d[j-1]],True)
def discover(d):
    candidates=[]
    for h,_ in Counter(d[i:i+2] for i in range(len(d)-1)).most_common(4):
        for k in MODELS:
            m=(h,k); f=frames(d,m);candidates.append((len(f),m))
    return sorted(candidates,reverse=True)
def gate(d,f):return len(f)>=8 and sum(j-i for i,j in f)/len(d)>=.65 and len({d[j-1] for i,j in f})>=4

def run():
    assert [check(b'123456789',k) for k in MODELS]==[0xf4,0x4b,0xdf]
    rows=[]
    for ix,k in enumerate([*MODELS,'outside']):
        for s in range(12):
            d,t=generate(82000+100*ix+s,k);a=len(d)//3;b=2*len(d)//3;actual={(i-b,j-b) for i,j in t if i>=b};v=d[a:b];test=d[b:];m=fit(d[:a],'joint');ev=evidence(v,m);old=m is not None and ev['n']>=8 and ev['coverage']>=.65 and ev['diversity']>=4
            candidates=[m for n,m in discover(d[:a]) if n>=8 and gate(v,frames(v,m))];accepted=len(candidates)==1;pred=set(frames(test,candidates[0])) if accepted else set(predict(test,m)) if old else set();rows.append(dict(kind=k,seed=s,old=old,new=accepted or old,crc_candidates=len(candidates),f1=2*len(pred&actual)/(len(pred)+len(actual))))
    summary={k:{x:statistics.mean(r[x] for r in rows if r['kind']==k) for x in ('old','new','f1')} for k in [*MODELS,'outside']};print(summary);json.dump(dict(summary=summary,rows=rows,reveng_available=bool(shutil.which('reveng'))),open('results_v08.json','w'),indent=2)
if __name__=='__main__':run()
