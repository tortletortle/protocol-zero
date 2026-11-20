import random, zlib, json, statistics, bisect
from collections import Counter
from itertools import accumulate

def checksum(b,k):
    if k=='sum':return sum(b)&255
    if k=='crc32low':return zlib.crc32(b)&255
    if k=='xor':
        v=0
        for x in b:v^=x
        return v
    if k=='crc8':
        v=0
        for x in b:
            v^=x
            for _ in range(8):v=((v<<1)^ (7 if v&128 else 0))&255
        return v
    return (255-sum(b))&255

def generate(seed,hard,unknown=False):
    r=random.Random(seed); h=r.randbytes(2); o=r.choice([2,3]); k='complement' if unknown else r.choice(['sum','crc32low','xor','crc8']); d=bytearray(r.randbytes(r.randrange(12))); truth=[]
    for _ in range(85):
        p=bytearray(r.randbytes(r.randrange(4,25)))
        if hard and r.random()<.65:p[:3]=h+bytes([4])
        b=h+(bytes([r.randrange(3)]) if o==3 else b'')+bytes([len(p)])+p; b+=bytes([checksum(b,k)])
        if hard and r.random()<.12:
            j=r.randrange(o+1,len(b)); b=b[:j]+b[j+1:]; d.extend(b)
        else:
            i=len(d);d.extend(b);truth.append((i,len(d)))
        if hard and r.random()<.18:d.extend(r.randbytes(r.randrange(1,5)))
    return bytes(d),truth,(h,o,o+2,k)

def edges(d,h,o,b):
    i=d.find(h)
    while i>=0:
        if i+o<len(d):
            j=i+d[i+o]+b
            if 7<=j-i<=32 and j<=len(d):yield i,j
        i=d.find(h,i+1)

def select(es,dp):
    es=sorted(es,key=lambda e:e[1]); ends=[j for i,j in es]
    if not dp:
        out=[];end=-1
        for i,j in es:
            if i>=end:out.append((i,j));end=j
        return out
    scores=[0];prev=[];take=[]
    for n,(i,j) in enumerate(es):
        p=bisect.bisect_right(ends,i,0,n); s=scores[p]+j-i
        take.append(s>scores[-1]);prev.append(p);scores.append(max(s,scores[-1]))
    out=[];n=len(es)
    while n:
        if take[n-1]:out.append(es[n-1]);n=prev[n-1]
        else:n-=1
    return out[::-1]

def infer(d,mode):
    hs=[h for h,n in Counter(d[i:i+2] for i in range(len(d)-1)).most_common(8)];best=None
    for h in hs:
        for o in (2,3):
            for b in (3,4,5,6):
                es=list(edges(d,h,o,b))
                for k in ([None] if mode=='no_checksum' else ['sum','crc32low','xor','crc8']):
                    valid=[(i,j) for i,j in es if k is None or checksum(d[i:j-1],k)==d[j-1]]
                    chosen=select(valid,mode=='dp');score=sum(j-i for i,j in chosen) if mode=='dp' else len(chosen)
                    if best is None or score>best[0]:best=(score,(h,o,b,k),len(chosen))
    if not best:return None
    if mode!='no_checksum' and best[2]<5:return None
    return best[1]

def predict(d,m,mode):
    if m is None:return []
    h,o,b,k=m;return select([(i,j) for i,j in edges(d,h,o,b) if k is None or checksum(d[i:j-1],k)==d[j-1]],mode=='dp')

def run():
    rows=[]
    for group in ('clean','hard','unknown'):
        for seed in range(41000,41060):
            d,t,m=generate(seed,group!='clean',group=='unknown');cut=len(d)//2; truth={(i-cut,j-cut) for i,j in t if i>=cut};row={'group':group,'seed':seed}
            for mode in ('no_checksum','greedy','dp'):
                model=infer(d[:cut],mode);p=set(predict(d[cut:],model,mode));row[mode]={'f1':2*len(p&truth)/(len(p)+len(truth)), 'structure':bool(model and model[:3]==m[:3]),'exact':model==m,'abstain':model is None}
            rows.append(row)
    summary={g:{m:{k:round(statistics.mean(r[m][k] for r in rows if r['group']==g),4) for k in ('f1','structure','exact','abstain')} for m in ('no_checksum','greedy','dp')} for g in ('clean','hard','unknown')};print(json.dumps(summary,indent=2));json.dump({'summary':summary,'rows':rows},open('results.json','w'),indent=2)
if __name__=='__main__':run()
