import random,json
from robust import infer
from relations import infer as exact

def run():
 out=[]
 for noise in (0,.05,.1,.2,.3):
  for kind in ('affine','xor','null'):
   counts=[0,0]; extras=0
   for seed in range(100):
    r=random.Random(13000+seed); a=r.randrange(1,256,2); b=r.randrange(256); rows=[]
    for t in range(128):
     x=r.randrange(256); y=(a*x+b)%256 if kind=='affine' else x^b if kind=='xor' else r.randrange(256)
     if r.random()<noise: y=r.randrange(256)
     rows.append(bytes((x,y)))
    p,q=rows[:64],rows[64:]; old=exact(p,q); new=infer(p,q)
    target=(0,1,'affine',a,b) if kind=='affine' else (0,1,'xor',b)
    normalized=[z[:5] if z[2]=='affine' else (z[0],z[1],z[2],z[4]) for z in new]
    counts[0]+=bool(old) if kind=='null' else target in old
    counts[1]+=bool(new) if kind=='null' else target in normalized
    extras+=len(new)>1
   out.append(dict(noise=noise,kind=kind,exact=counts[0],robust=counts[1],multiple=extras,n=100))
 return out
if __name__=='__main__': print(json.dumps(run(),indent=2))
