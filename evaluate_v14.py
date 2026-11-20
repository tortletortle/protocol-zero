import random,json
from adaptive import infer
from robust import infer as baseline

def run():
 out=[]
 for noise in (0,.1,.2,.3,.5,.7):
  for kind in ('affine','null','biased_null'):
   old=new=0
   for seed in range(40):
    rng=random.Random(14000+seed); rows=[]
    for t in range(128):
     x=rng.randrange(256) if kind!='biased_null' else rng.choice([0]*9+list(range(1,16)))
     y=(7*x+31)%256 if kind=='affine' else rng.randrange(256) if kind=='null' else rng.choice([0]*9+list(range(1,16)))
     if rng.random()<noise: y=rng.randrange(256)
     rows.append(bytes((x,y)))
    p,q=rows[:64],rows[64:]; a=baseline(p,q); b=infer(p,q,permutations=199,seed=seed)
    old+=any(z[:5]==(0,1,'affine',7,31) for z in a) if kind=='affine' else bool(a)
    new+=any(z[:5]==(0,1,'affine',7,31) for z in b) if kind=='affine' else bool(b)
   out.append(dict(noise=noise,kind=kind,n=40,baseline=old,adaptive=new))
 return out
if __name__=='__main__': print(json.dumps(run(),indent=2))
