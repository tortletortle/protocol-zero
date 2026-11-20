"""Independent runs; independent blocks within train/validation; burst replacement."""
import json,random
from adaptive import infer as row_test
from temporal import infer


def samples(seed,kind,block_size=8,blocks=32):
    rng=random.Random(seed); a=rng.choice([3,5,7,9,11,13]); b=rng.randrange(256)
    def split():
        rows=[]
        for _ in range(blocks):
            x=rng.randrange(16); y=rng.randrange(16)
            if kind=='affine_burst':
                y=(a*x+b)%256 if rng.random()>=.3 else rng.randrange(256)
            for k in range(block_size):
                rows.append(bytes((x,y)))
        return rows
    return split(),split(),(a,b)


def run(n=100):
    out=[]
    for kind in ('independent_blocks','affine_burst'):
        for size in (1,4,8,16):
            old=new=0
            for seed in range(n):
                p,q,(a,b)=samples(15000+seed,kind,size)
                r=row_test(p,q,permutations=199,seed=seed)
                s=infer(p,q,size,permutations=199,seed=seed)['edges']
                if kind=='independent_blocks':
                    old+=bool(r); new+=bool(s)
                else:
                    old+=any(z[:5]==(0,1,'affine',a,b) for z in r)
                    new+=any((z['kind'],z['a'],z['b'])==('affine',a,b) for z in s)
            out.append(dict(kind=kind,block_size=size,n=n,row=old,block=new))
    return out
if __name__=='__main__': print(json.dumps(run(),indent=2))
