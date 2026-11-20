"""Disjoint passive sessions; synthetic opcode and alias stress controls."""
import json,random
from collections import Counter
from message_types import infer,events
from session_model import fit,assess


def sample(r,kind,n,invalid=False,shift=False):
    rows=[]; session_id=r.randrange(4)
    for i in range(n):
        v=r.randrange(2)
        for d,code in [('C',1+v),('S',2),('C',16+(1-v if invalid and i==0 else v)),('S',32)]:
            actual=r.randrange(4) if kind=='null' else code
            proxy=(actual^85) if kind=='alias' or (kind=='shift' and not shift) else r.randrange(4)
            frame=bytes([165,session_id,actual,r.randrange(4),proxy])+r.randbytes(5)
            rows.append((d,frame))
    return rows


def run(n=40):
    out=[]
    for kind in ('clean','alias','shift','null'):
        c=Counter()
        for seed in range(n):
            r=random.Random(23000+seed)
            a=[sample(r,kind,4) for _ in range(24)]; b=[sample(r,kind,5) for _ in range(12)]
            p=[sample(r,kind,6,shift=True) for _ in range(20)]; q=[sample(r,kind,6,True,True) for _ in range(20)]
            cand=infer(a,b); offsets=[x['offset'] for x in cand]
            c['any_candidate']+=bool(offsets); c['true_offset']+=2 in offsets
            c['unique_true']+=offsets==[2]; c['alias_present']+=4 in offsets
            for o in offsets:
                m=fit([events(s,o) for s in a],2)
                pos=sum(assess(m,events(s,o))['status']=='consistent_with_model' for s in p)
                neg=sum(assess(m,events(s,o))['status']=='unseen_transition' for s in q)
                if o==2: c['true_positive_accept']+=pos; c['true_negative_flag']+=neg
                elif o==4: c['alias_positive_accept']+=pos; c['alias_negative_flag']+=neg
        out.append(dict(kind=kind,n=n,positive_per_kind=n*20,negative_per_kind=n*20,**c))
    return out

if __name__=='__main__': print(json.dumps(run(),indent=2))
