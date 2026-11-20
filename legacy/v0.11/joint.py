import random,statistics,json
from collections import Counter
from benchmark import edges,select,checksum

def generate(seed,group):
 r=random.Random(seed); h=r.randbytes(2); o=r.choice([2,3]); t=r.randrange(3); l=r.randrange(3); a=r.randrange(1,256); b=r.randrange(256); d=bytearray(r.randbytes(r.randrange(12))); truth=[]
 for _ in range(75):
  p=bytearray(r.randbytes(r.randrange(5,21)))
  if group!='clean' and r.random()<.35:p[:2]=h
  q=h+(r.randbytes(1) if o==3 else b'')+bytes([len(p)])+p
  c=(a*sum(q[l:])+b)%256 if group!='outside' else checksum(q[l:],'crc8')
  q=q[:len(q)-t]+bytes([c])+q[len(q)-t:]
  i=len(d);d.extend(q);truth.append((i,len(d)))
  if group!='clean' and r.random()<.15:d.extend(r.randbytes(r.randrange(1,5)))
 return bytes(d),truth

def observations(d,es,l,t):
 out=[]
 for i,j in es:
  q=d[i:j]; k=len(q)-1-t
  if k>=l:out.append(((sum(q[l:k])+sum(q[k+1:]))%256,q[k]))
 return out

def fit(d,mode):
 best=None
 for h,_ in Counter(d[i:i+2] for i in range(len(d)-1)).most_common(4):
  for o in (2,3):
   for extra in (3,4,5):
    es=list(edges(d,h,o,extra));
    if len(es)<8:continue
    for l in range(3):
     for t in range(3):
      p=observations(d,es,l,t)
      if not p:continue
      # deterministic seed subset; robust to false candidates
      for a in (range(256) if mode=='joint' else (1,)):
       counts=Counter((y-a*x)%256 for x,y in p);b,n=counts.most_common(1)[0]
       if a==0 or n<8 or n<len(es)*.45:continue
       # number of mutually consistent frames, penalize constant models
       score=(n,-int(a==0))
       if best is None or score>best[0]:best=(score,(h,o,extra,l,t,a,b))
 return best[1] if best else None

def predict(d,m):
 if m is None:return []
 h,o,e,l,t,a,b=m;es=list(edges(d,h,o,e));return select([ij for ij,(x,y) in zip(es,observations(d,es,l,t)) if (a*x+b)%256==y],True)

def run():
 rows=[]
 for g in ('clean','noise','outside'):
  for s in range(61000,61012):
   d,truth=generate(s+1000*('clean','noise','outside').index(g),g);cut=len(d)//2;actual={(i-cut,j-cut) for i,j in truth if i>=cut}; row={'group':g,'seed':s}
   for mode in ('restricted','joint'):
    m=fit(d[:cut],mode);p=set(predict(d[cut:],m));row[mode]={'f1':2*len(p&actual)/(len(p)+len(actual)),'accepted':m is not None}
   rows.append(row)
 summary={g:{m:{k:statistics.mean(r[m][k] for r in rows if r['group']==g) for k in ('f1','accepted')} for m in ('restricted','joint')} for g in ('clean','noise','outside')};print(summary);json.dump({'summary':summary,'rows':rows},open('results.json','w'),indent=2)
if __name__=='__main__':run()
