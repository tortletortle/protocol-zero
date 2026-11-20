"""Known-format controlled fixtures, not external capture evidence."""
import json,random
from length_rules import infer
from fields import infer as baseline


def run(n=50):
    out=[]
    for family in ('short','long','little','null','fixed'):
        old=new=ambiguous=0
        for seed in range(n):
            rng=random.Random(17000+seed); rows=[]
            endian='little' if family=='little' else 'big'
            for i in range(48):
                size=8 if family=='fixed' else rng.randint(4,32) if family=='short' else rng.randint(4,500)
                data=rng.randbytes(size); length=size+2 if family!='null' else rng.randrange(65536)
                rows.append(rng.randbytes(2)+b'\0\0'+length.to_bytes(2,endian)+b'\x01\x03'+data)
            p,q=rows[:24],rows[24:]; r=infer(p,q)
            target=dict(offset=4,width=2,endian=endian,bias=6)
            old+=any(x[:2]==(4,6) and x[2]=='length' for x in baseline(p))
            new+=bool(r['rules']) if family in ('null','fixed') else target in r['rules']
            ambiguous+=len(r['rules'])>1
        out.append(dict(family=family,n=n,baseline=old,new=new,ambiguous=ambiguous))
    return out
if __name__=='__main__': print(json.dumps(run(),indent=2))
