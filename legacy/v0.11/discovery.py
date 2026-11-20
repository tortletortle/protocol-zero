import random,json,statistics,math
from benchmark import checksum

def points(frames,l,t):
 return [(sum(f[l:len(f)-1-t])%256,f[-1]) for f in frames]
def fit(frames):
 models=[]
 for l in range(5):
  for t in range(3):
   p=points(frames,l,t); x,y=p[0]
   for a in range(256):
    b=(y-a*x)%256
    if all((a*u+b)%256==v for u,v in p):models.append((l,t,a,b))
 return models
def valid(frames,m):
 l,t,a,b=m
 return all((a*x+b)%256==y for x,y in points(frames,l,t))
def run():
 rows=[]
 for group in ('known','affine','outside'):
  for seed in range(53000,53060):
   r=random.Random(seed+1000*('known','affine','outside').index(group)); l,t=r.randrange(5),r.randrange(3);a,b=r.randrange(1,256),r.randrange(256)
   if group=='known':l,t,a,b=0,0,1,0
   truth=(l,t,a,b); frames=[]
   for _ in range(60):
    p=r.randbytes(r.randrange(10,35)); c=((a*sum(p[l:len(p)-t])+b)%256 if group!='outside' else checksum(p,'crc8'));frames.append(p+bytes([c]))
   train,validation,test=frames[:20],frames[20:40],frames[40:]; models=[m for m in fit(train) if valid(validation,m)]; chosen=models[0] if len(models)==1 else None
   baseline=next((k for k in ('sum','xor','crc8','crc32low') if all(checksum(f[:-1],k)==f[-1] for f in train+validation)),None)
   rows.append(dict(group=group,seed=seed,truth=truth,models=models,chosen=chosen,exact=chosen==truth and group!='outside',accepted=chosen is not None,test_ok=chosen is not None and valid(test,chosen),baseline_ok=baseline is not None and all(checksum(f[:-1],baseline)==f[-1] for f in test)))
 summary={g:{k:sum(r[k] for r in rows if r['group']==g) for k in ('exact','accepted','test_ok','baseline_ok')} for g in ('known','affine','outside')}; print(summary);json.dump(dict(summary=summary,rows=rows),open('discovery_results.json','w'),indent=2)
if __name__=='__main__':run()
