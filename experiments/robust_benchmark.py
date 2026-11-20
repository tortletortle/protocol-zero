"""Paired regression and fresh synthetic stress; thresholds fixed before holdout."""
import csv,json,random,statistics,time,sys
from pathlib import Path
from joint_crc_stress import capture as prior_capture,setup
from joint_crc_benchmark import independent,f1
from protocol_zero import joint_crc,robust_crc


def capture(l,m,seed,count,kind):
    r=random.Random(seed);out=bytearray(r.randbytes(7));truth=set()
    for i in range(count):
        size=r.randrange(4,65);body=l.sync+bytes([i%256,size])+r.randbytes(size)
        val=(sum(x*x for x in body)+17)%256 if kind=='outside' else independent(body,m)
        q=bytearray(body+bytes([val]));good=True
        if kind in ('sparse','heavy','over_limit') and r.random()<{'sparse':.12,'heavy':.25,'over_limit':.45}[kind]:
            q[r.randrange(4,len(q)-1)]^=1<<r.randrange(8);good=False
        if kind=='mixed' and r.random()<.18:
            if r.random()<.5:del q[r.randrange(4,len(q)-1)]
            else:q[r.randrange(4,len(q)-1)]^=1
            good=False
        a=len(out);out.extend(q)
        if good:truth.add((a,len(out)))
        out.extend(r.randbytes(r.randrange(0,6)))
    return bytes(out),truth


def run(selected=None):
    rows=[]
    for kind,seeds in [('regression',range(82600,82612))]+[(k,range(85100,85108)) for k in ('clean','sparse','heavy','mixed','over_limit','outside')]:
        if selected and kind!=selected: continue
        for seed in seeds:
            l,m=setup(seed,'unknown'); gen=prior_capture if kind=='regression' else capture
            scenario='sparse_noise' if kind=='regression' else kind
            a,_=gen(l,m,seed+10000,60,scenario);b,_=gen(l,m,seed+20000,40,scenario);c,t=gen(l,m,seed+30000,50,scenario)
            row=dict(kind=kind,seed=seed)
            for name,fn in [('old',joint_crc.infer),('new',robust_crc.infer)]:
                now=time.perf_counter();fit=fn([a],[b]);elapsed=time.perf_counter()-now
                pred=set(joint_crc.decode(c,fit['models'])['agreed'])
                values=dict(status=fit['status'],accepted=bool(fit['models']),retained=kind!='outside' and any(q==l and m in ms for q,ms in fit['models']),f1=f1(pred,t),false_spans=len(pred-t),seconds=round(elapsed,6),votes=fit.get('search',{}).get('votes',0))
                row.update({name+'_'+k:v for k,v in values.items()})
            rows.append(row)
        print(kind,[(k,sum(r[k] for r in rows if r['kind']==kind)) for k in ('old_accepted','new_accepted','old_retained','new_retained','old_false_spans','new_false_spans')],flush=True)
    root=Path(__file__).parent
    with (root/('v025_'+selected+'.csv' if selected else 'v025_trials.csv')).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={}
    for kind in dict.fromkeys(r['kind'] for r in rows):
        rr=[r for r in rows if r['kind']==kind];result[kind]={'n':len(rr)}
        for prefix in ('old','new'):
            result[kind][prefix]={k:sum(r[prefix+'_'+k] for r in rr) for k in ('accepted','retained','false_spans')}
            result[kind][prefix].update({k:round(statistics.mean(r[prefix+'_'+k] for r in rr),6) for k in ('f1','seconds','votes')})
            result[kind][prefix]['budget_exceeded']=sum(r[prefix+'_status']=='budget_exceeded' for r in rr)
    (root/('v025_'+selected+'.json' if selected else 'v025_summary.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else None)
