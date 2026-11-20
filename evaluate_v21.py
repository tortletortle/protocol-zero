"""Controlled session grammar benchmark with disjoint session-length ranges."""
import json,random
from collections import Counter
from session_model import fit,assess,choose,symbols
from pipeline import analyze
from protocol_spec import export,load


def session(r,n,invalid=False):
    out=[]
    for i in range(n):
        v=r.randrange(2)
        out += ['C:%02x'%(1+v),'S:02','C:%02x'%(0x10+v+(1-2*v if invalid and i==0 else 0)),'S:20']
    return out


def accepted(m,s):
    return assess(m,s)['status']=='consistent_with_model'


def run(n=40):
    total={k:Counter() for k in ('prefix','depth1','depth2','positive_only','labeled')}
    for seed in range(n):
        r=random.Random(22000+seed)
        train=[session(r,r.randint(1,3)) for _ in range(24)]
        vp=[session(r,r.randint(2,4)) for _ in range(12)]; vn=[session(r,r.randint(2,4),True) for _ in range(12)]
        tp=[session(r,r.randint(5,7)) for _ in range(20)]; tn=[session(r,r.randint(5,7),True) for _ in range(20)]
        # Prefix-tree cannot generalize to strictly longer sessions.
        models={'prefix':fit(train,None),'depth1':fit(train,1),'depth2':fit(train,2),
                'positive_only':choose(train,vp)[0],'labeled':choose(train,vp,vn)[0]}
        for k,m in models.items():
            total[k]['positive_accept']+=sum(accepted(m,s) for s in tp)
            total[k]['negative_flag']+=sum(not accepted(m,s) for s in tn)
            total[k]['states_sum']+=len(m['transitions'])
            total[k]['depth2_selected']+=m['depth']==2
    return dict(seeds=n,positive_per_method=n*20,negative_per_method=n*20,methods=total)


def end_to_end():
    """Existing framing learner -> spec -> externally ordered directional bursts -> model."""
    r=random.Random(42)
    def encode(s):
        out=[]
        for event in s:
            d,code=event.split(':'); n=r.randint(5,30)
            body=bytes([165,90,n,int(code,16)])+r.randbytes(n-1)
            out.append((d,body+bytes([sum(body)%256])))
        return out
    tr=[session(r,3) for _ in range(24)]; va=[session(r,3) for _ in range(12)]
    a=[encode(s) for s in tr]; b=[encode(s) for s in va]
    spec=load(json.dumps(export(analyze([b''.join(f for d,f in s) for s in a], [b''.join(f for d,f in s) for s in b]))))
    def extract(sessions):
        arr=[]
        for bursts in sessions:
            x=symbols(spec,bursts,3)
            if x['status']!='ok' or x['unchecked']: raise AssertionError(x)
            arr.append(x['events'])
        return arr
    m=fit(extract(a),2)
    pos=[session(r,5) for _ in range(20)]; neg=[session(r,5,True) for _ in range(20)]
    p=extract([encode(s) for s in pos]); q=extract([encode(s) for s in neg])
    return dict(exact_symbols=p==pos and q==neg,positive_accept=sum(accepted(m,s) for s in p),negative_flag=sum(not accepted(m,s) for s in q),n_each=20)

if __name__=='__main__': print(json.dumps(dict(benchmark=run(),integration=end_to_end()),indent=2))
