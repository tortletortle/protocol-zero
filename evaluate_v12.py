import random,json
from relations import infer,counters

def run():
 out={}
 for kind in ('affine','xor','independent','shift'):
  hits=0
  for seed in range(100):
   rng=random.Random(seed); a=rng.randrange(1,256,2); b=rng.randrange(256); start=rng.randrange(65536); step=rng.randrange(2,16)
   rows=[]
   for t in range(64):
    x=rng.randrange(256)
    y=(a*x+b)%256 if kind=='affine' else x^b if kind=='xor' else rng.randrange(256)
    rows.append(bytes((x,y)) if kind!='shift' else bytes((x,))+((start+t*step)%65536).to_bytes(2,'little'))
   pred=infer(rows[:32],rows[32:]) if kind!='shift' else counters(rows[:32],rows[32:])
   target=(0,1,'affine',a,b) if kind=='affine' else (0,1,'xor',b) if kind=='xor' else (1,2,'little',step)
   hits+=bool(pred) if kind=='independent' else target in pred
  out[kind]=hits
 return out
if __name__=='__main__': print(json.dumps(run(),indent=2))
