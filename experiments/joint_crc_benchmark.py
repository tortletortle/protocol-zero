"""Synthetic paired benchmark with independent polynomial division generator."""
import csv,json,random,statistics,sys,time
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol_zero.joint_crc import Layout,infer,decode
from protocol_zero.crc_discovery import CRCModel
from protocol_zero.equivalence import fit_models,consensus
from protocol_zero.checksums import checksum

SCENARIOS=('preset','unknown','noise','wide','suffix','outside','unique_lengths','fixed','decoys')
SEEDS=range(82500,82512)


def independent(body,m):
    v=(m.init<<(8*len(body)))^(int.from_bytes(body,'big')<<8)
    for bit in range(v.bit_length()-1,7,-1):
        if v&(1<<bit):v^=(256|m.poly)<<(bit-8)
    return v^m.xorout


def setup(seed,kind):
    r=random.Random(seed);sync=r.randbytes(2)
    wide=kind=='wide';suffix=int(kind=='suffix');start=2 if kind in ('wide','suffix') else 0
    m=CRCModel(7,0,0) if kind=='preset' else CRCModel(r.choice([p for p in range(3,256,2) if p not in (7,29,47)]),r.randrange(256),r.randrange(256))
    l=Layout(sync,3,2 if wide else 1,'big' if wide else 'little',5 if wide else 4,suffix,start)
    return l,m


def capture(l,m,seed,n,kind):
    r=random.Random(seed);out=bytearray(r.randbytes(7));truth=[]
    for i in range(n):
        size=12 if kind=='fixed' else i+8 if kind=='unique_lengths' else (12,19,270)[i%3] if l.width==2 else (8,13,22)[i%3]
        p=bytearray(r.randbytes(size))
        if kind=='decoys' and i%5==0:p[3:5]=l.sync
        body=l.sync+bytes([i%256])+size.to_bytes(l.width,l.endian)+p
        c=(sum(x*x for x in body[l.coverage_start:])+17)%256 if kind=='outside' else independent(body[l.coverage_start:],m)
        word=bytearray(body+bytes([c])+r.randbytes(l.suffix));good=True
        if kind=='noise' and i%9==3:word[-2]^=1;good=False
        a=len(out);out.extend(word)
        if good:truth.append((a,len(out)))
        out.extend(r.randbytes(r.randrange(0,4)))
    return bytes(out),set(truth)


def f1(pred,t):return 2*len(pred&t)/max(1,len(pred)+len(t))


def run():
    rows=[]
    for kind in SCENARIOS:
        for seed in SEEDS:
            l,m=setup(seed,kind);a,_=capture(l,m,seed+10000,36,kind);b,_=capture(l,m,seed+20000,24,kind);c,t=capture(l,m,seed+30000,30,kind)
            now=time.perf_counter()
            with patch('protocol_zero.framing.checksum',lru_cache(maxsize=20000)(checksum)):
                old=fit_models([a],[b],sync_limit=6)
            old_s=time.perf_counter()-now;now=time.perf_counter();fit=infer([a],[b]);new_s=time.perf_counter()-now
            oldp={(r['start'],r['end']) for r in consensus(c,old['models'])['agreed']}
            result=decode(c,fit['models']);newp=set(result['agreed']);allp=newp|{(x,y) for x,y,_ in result['contested']}
            rows.append(dict(scenario=kind,seed=seed,status=fit['status'],old_status=old['status'],old_f1=f1(oldp,t),new_f1=f1(newp,t),possible_recall=len(allp&t)/len(t),false_agreed=len(newp-t),model_groups=len(fit['models']),true_retained=kind!='outside' and any(q==l and m in ms for q,ms in fit['models']),old_seconds=round(old_s,6),new_seconds=round(new_s,6)))
        print(kind,'complete',flush=True)
    root=Path(__file__).parent
    with (root/'v024_trials.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={}
    for kind in SCENARIOS:
        rs=[r for r in rows if r['scenario']==kind]
        result[kind]=dict(n=len(rs),accepted=sum(r['model_groups']>0 for r in rs),true_retained=sum(r['true_retained'] for r in rs),false_agreed=sum(r['false_agreed'] for r in rs),**{k:round(statistics.mean(r[k] for r in rs),6) for k in ('old_f1','new_f1','possible_recall','old_seconds','new_seconds')})
    (root/'v024_summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':run()
