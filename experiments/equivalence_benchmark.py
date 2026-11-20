"""Synthetic matched holdout: one size request, up to three complete frames."""
import sys, csv, json, random, statistics, time
from functools import lru_cache
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol_zero.model import FrameModel
from protocol_zero.framing import infer_model, decode_stream, rank_hypotheses
from protocol_zero.checksums import checksum
from protocol_zero.equivalence import fit_models, consensus, plan_lengths, refine
# Independent bit-wise generator, reused from the V0.2.1 local benchmark.
def check(b,name):
    if name=='sum8':return sum(b)%256
    if name=='xor8':
        n=0
        for x in b:n^=x
        return n
    p,reg,xor={'crc8_smbus':(7,0,0),'crc8_j1850':(29,255,255),'crc8_autosar':(47,255,255)}[name]
    for x in b:
        for bit in range(7,-1,-1):
            feedback=((reg>>7)^((x>>bit)&1))&1
            reg=(reg*2)%256
            if feedback:reg^=p
    return reg^xor


SCENARIOS=('short_le_wide','short_le_narrow','short_be_wide','short_be_narrow','symmetric_wide','diverse_wide','outside_checksum')
SEEDS=range(62100,62106)
ARMS=('none','random','longest','planner')
def descriptor(seed,scenario):
    sync=random.Random(seed).randbytes(2)
    if sync in (b'\0\0',b'\xff\xff'):sync=b'\xa6\x39'
    width=1 if 'narrow' in scenario else 2
    endian='big' if '_be_' in scenario or (scenario=='symmetric_wide' and seed%2) else 'little'
    offset=3 if width==1 and endian=='big' else 2
    m=FrameModel(sync,offset,width,endian if width==2 else 'little',4,1,'crc8_smbus')
    lengths=[0,257] if scenario=='symmetric_wide' else [7,13,29,270] if scenario=='diverse_wide' else [7,13,29]
    allowed=[21,45,262] if scenario=='symmetric_wide' else [12,18,34,84,132,200,261,278,324]
    return m,lengths,allowed

def pack(m,n,r,outside=False):
    h=bytearray(m.payload_offset);h[:2]=m.sync
    h[m.length_offset:m.length_offset+m.length_width]=n.to_bytes(m.length_width,m.length_endian)
    body=bytes(h)+r.randbytes(n)
    c=(sum(x*x for x in body)+17)%256 if outside else check(body,m.checksum)
    return body+bytes([c])

def capture(m,lengths,seed,count,outside=False):
    r=random.Random(seed);out=bytearray(r.randbytes(5));truth=[]
    for i in range(count):
        q=pack(m,lengths[i%len(lengths)],r,outside);a=len(out);out.extend(q);truth.append((a,len(out)))
        if r.random()<0.2:out.extend(r.randbytes(r.randrange(1,4)))
    return bytes(out),set(truth)

def f1(pred,truth):return 2*len(pred&truth)/max(1,len(pred)+len(truth))

def run():
    rows=[];start=time.perf_counter()
    for scenario in SCENARIOS:
        for seed in SEEDS:
            m,lengths,allowed=descriptor(seed,scenario);outside=scenario=='outside_checksum'
            train,_=capture(m,lengths,seed+100000,36,outside);val,_=capture(m,lengths,seed+200000,24,outside);test,truth=capture(m,lengths,seed+300000,30,outside)
            # Identical, memoized checksum function; both decision arms see exactly
            # the same ranked input. No ground truth enters model selection.
            with patch('protocol_zero.framing.checksum',lru_cache(maxsize=20000)(checksum)):
                ranked=rank_hypotheses([train],[val])
            with patch('protocol_zero.framing.rank_hypotheses',return_value=ranked), patch('protocol_zero.equivalence.rank_hypotheses',return_value=ranked):
                old=infer_model([train],[val]);om=old['model'];fit=fit_models([train],[val]);ms=fit['models']
            before={(x.start,x.end) for x in decode_stream(test,om)['frames']} if om else set()
            agreed={(x['start'],x['end']) for x in consensus(test,ms)['agreed']}
            row=dict(scenario=scenario,seed=seed,old_status=old['status'],new_status=fit['status'],old_f1=f1(before,truth),new_f1=f1(agreed,truth),false_spans=len(agreed-truth),candidates=len(ms),truth_retained=not outside and m in ms,old_correct=not outside and om==m,old_wrong=om is not None and (outside or om!=m),new_unique_correct=not outside and ms==[m],new_unique_wrong=len(ms)==1 and (outside or ms[0]!=m))
            plan=plan_lengths(ms,allowed)
            sizes={'none':None,'random':random.Random(seed+400000).choice(allowed),'longest':max(allowed),'planner':plan[0]['total_size'] if plan else None}
            for arm,size in sizes.items():
                frames=[];no_response=False
                if size is not None and len(ms)>1:
                    n=size-m.payload_offset-m.trailer_size
                    if 0<=n<=min(m.max_payload,2**(8*m.length_width)-1):
                        rng=random.Random(seed+500000+size);frames=[pack(m,n,rng,outside) for _ in range(3)]
                    else:no_response=True
                ref=refine(ms,frames);kept=ref['models']
                row.update({arm+'_size':size,arm+'_observations':len(frames),arm+'_no_response':no_response,arm+'_status':ref['status'],arm+'_n':len(kept),arm+'_correct':not outside and kept==[m] and (len(ms)==1 or ref['status']=='unique_under_observations'),arm+'_wrong':len(kept)==1 and (outside or kept[0]!=m),arm+'_retained':not outside and m in kept})
            rows.append(row)
        print(scenario,'completed',flush=True)
    summary={}
    for scenario in SCENARIOS:
        rs=[r for r in rows if r['scenario']==scenario];amb=[r for r in rs if r['candidates']>1]
        summary[scenario]=dict(n=len(rs),ambiguous=len(amb),old_f1=statistics.mean(r['old_f1'] for r in rs),new_f1=statistics.mean(r['new_f1'] for r in rs),**{k:sum(r[k] for r in rs) for k in ('false_spans','truth_retained','old_correct','old_wrong','new_unique_correct','new_unique_wrong')},rejected=sum(r['candidates']==0 for r in rs),arms={a:{k:sum(r[a+'_'+k] for r in amb) for k in ('correct','wrong','no_response','retained')} for a in ARMS})
    out=dict(protocol=dict(seeds=list(SEEDS),scenarios=list(SCENARIOS),capture_counts=[36,24,30],acquisition_budget='one size, up to three complete frames; silence is not evidence',scope='synthetic only; in-family and unknown-checksum controls'),summary=summary,rows=rows,seconds=time.perf_counter()-start)
    root=Path(__file__).parent;(root/'v022_results.json').write_text(json.dumps(out,indent=2))
    with (root/'v022_results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':run()
