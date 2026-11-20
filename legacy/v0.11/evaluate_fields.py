import random,json,statistics
from fields import infer
from evaluate_v08 import discover,frames,gate

def generate(seed,kind):
 r=random.Random(seed);h=r.randbytes(2); raw=[]; start=r.randrange(240,256) if kind!='no_wrap' else r.randrange(20); w=1 if kind=='byte' else 2; e='big' if kind=='big' else 'little'; truth=[(0,2,'constant'),(2,3,'length'),(3,3+w,'counter'+str(w)+e),(3+w,-1,'unknown'),(-1,0,'checksum_candidate')]
 for j in range(100):
  p=((start+j)%256**w).to_bytes(w,e)+r.randbytes(r.randrange(5,15)); q=h+bytes([len(p)])+p
  # independent CRC implementation, polynomial long division
  x=int.from_bytes(q,'big')<<8
  for bit in range(x.bit_length()-1,7,-1):
   if x&(1<<bit):x^=0x107<<(bit-8)
  raw.append(q+bytes([x]))
 return raw,truth

def score(p,t):
 p=set(p);t=set(t);return 2*len(p&t)/(len(p)+len(t))
def run():
 rows=[]
 for k in ('byte','little','big','no_wrap'):
  for s in range(20):
   raw,t=generate(93000+s,k); d=b''.join(raw[:60]);v=b''.join(raw[60:80]);test=b''.join(raw[80:]); cand=[m for n,m in discover(d) if n>=8 and gate(v,frames(v,m))];pred=[]; recovered=[]
   if len(cand)==1:
    m=cand[0]; train=[d[i:j] for i,j in frames(d,m)];pred=infer(train); recovered=[test[i:j] for i,j in frames(test,m)]
   baseline=[(0,2,'constant'),(2,3,'length'),(3,4,'counter1little'),(4,-1,'unknown'),(-1,0,'checksum_candidate')]
   rows.append(dict(kind=k,seed=s,exact=pred==t,f1=score(pred,t),baseline=score(baseline,t),framing=recovered==raw[80:],prediction=pred,truth=t))
 summary={k:{x:statistics.mean(r[x] for r in rows if r['kind']==k) for x in ('exact','f1','baseline','framing')} for k in ('byte','little','big','no_wrap')}; print(summary);json.dump(dict(summary=summary,rows=rows),open('results_v09.json','w'),indent=2)
if __name__=='__main__':run()
