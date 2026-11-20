"""Independent synthetic holdout; one extra complete observation per arm."""
import csv
import json
import random
import statistics
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol_zero.crc_discovery import CRCModel, discover, groups, plan, refine

SCENARIOS = ('known_crc','unknown_variable','unknown_fixed','equivalent_parameters','outside_nonlinear','corrupted_validation')
SEEDS = range(73200,73212)


def independent(body, m):
    # Polynomial long division, independent of the inference lookup table.
    v = (m.init << (8*len(body))) ^ (int.from_bytes(body,'big') << 8)
    for bit in range(v.bit_length()-1,7,-1):
        if v & (1 << bit):
            v ^= (256 | m.poly) << (bit-8)
    return v ^ m.xorout


def run():
    rows = []
    for kind in SCENARIOS:
        for seed in SEEDS:
            rng = random.Random(seed)
            poly = rng.choice([p for p in range(1,256,2) if p not in (7,29,47)])
            m = CRCModel(poly,rng.randrange(256),rng.randrange(256))
            if kind == 'known_crc': m=CRCModel(7,0,0)
            if kind == 'unknown_fixed': m=CRCModel(29,rng.randrange(256),rng.randrange(256))
            if kind == 'equivalent_parameters': m=CRCModel(7,rng.randrange(256),rng.randrange(256))
            def encode(b):
                c = (sum(x*x for x in b)+17)%256 if kind=='outside_nonlinear' else independent(b,m)
                return b+bytes([c])
            sizes = [8]*12 if kind=='unknown_fixed' else [5,6,7,8]*3
            a = [encode(rng.randbytes(n)) for n in sizes]
            b = [encode(rng.randbytes(n)) for n in sizes[:8]]
            if kind=='corrupted_validation': b[0]=b[0][:-1]+bytes([b[0][-1]^1])
            test = [encode(rng.randbytes(n)) for n in [9,12,17,33,56,120,256]]
            result=discover(a,b); ms=result['models']; cls=groups(ms)
            supported=kind not in ('outside_nonlinear','corrupted_validation')
            row=dict(scenario=kind,seed=seed,status=result['status'],preset_accepted=bool(result['presets']),
                     parameters=len(ms),classes=len(cls),true_retained=supported and m in ms,
                     unique_correct=supported and len(cls)==1 and m in ms,
                     unique_wrong=len(cls)==1 and (not supported or m not in ms),
                     all_test_predict=bool(ms) and all(all(x.predict(w[:-1])==w[-1] for w in test) for x in ms))
            bodies=[rng.randbytes(n) for n in (8,9,263)]
            p=plan(ms,bodies)
            choices={'none':None,'random':random.Random(seed+10000).choice(bodies),'longest':bodies[-1],
                     'planner':bytes.fromhex(p[0]['body_hex']) if p else None}
            for arm,body in choices.items():
                rr=refine(ms,[encode(body)] if body is not None and len(cls)>1 else [])
                row[arm+'_classes']=len(groups(rr))
                row[arm+'_correct']=supported and m in rr and len(groups(rr))==1
                row[arm+'_wrong']=len(groups(rr))==1 and (not supported or m not in rr)
            rows.append(row)
    summary={}
    for kind in SCENARIOS:
        rr=[r for r in rows if r['scenario']==kind]
        summary[kind]={k:sum(r[k] for r in rr) for k in ('preset_accepted','true_retained','unique_correct','unique_wrong','all_test_predict','none_correct','random_correct','longest_correct','planner_correct','planner_wrong')}
        summary[kind].update(n=len(rr),rejected=sum(r['status']=='rejected' for r in rr),mean_classes=statistics.mean(r['classes'] for r in rr))
    root=Path(__file__).parent
    with (root/'v023_trials.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (root/'v023_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': run()
