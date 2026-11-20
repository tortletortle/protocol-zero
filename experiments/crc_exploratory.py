"""Exploratory stress test with randomized polynomial and allowed lengths."""
import csv
import random
import statistics
from pathlib import Path
from crc_benchmark import independent
from protocol_zero.crc_discovery import CRCModel, discover, groups, plan, refine


def run():
    rows=[]
    for seed in range(73300,73340):
        r=random.Random(seed)
        m=CRCModel(r.randrange(1,256,2),r.randrange(256),r.randrange(256))
        n=r.randrange(6,20)
        def encode(b):return b+bytes([independent(b,m)])
        a=[encode(r.randbytes(n)) for _ in range(12)]
        b=[encode(r.randbytes(n)) for _ in range(8)]
        ms=discover(a,b)['models']
        bodies=[r.randbytes(k) for k in sorted({n,*[r.randrange(1,513) for _ in range(5)]})]
        p=plan(ms,bodies)
        arms={'random':random.Random(seed+500).choice(bodies),'longest':bodies[-1],
              'planner':bytes.fromhex(p[0]['body_hex']) if p else None}
        row=dict(seed=seed,poly=m.poly,initial_classes=len(groups(ms)),truth_retained=m in ms)
        for name,body in arms.items():
            remaining=refine(ms,[encode(body)] if body is not None else [])
            row[name+'_classes']=len(groups(remaining))
            row[name+'_unique']=m in remaining and len(groups(remaining))==1
            row[name+'_wrong']=m not in remaining
        rows.append(row)
    path=Path(__file__).parent/'v023_exploratory.csv'
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    ambiguous=[r for r in rows if r['initial_classes']>1]
    print('ambiguous',len(ambiguous),'truth retained',sum(r['truth_retained'] for r in rows))
    for arm in ('random','longest','planner'):
        print(arm,'unique',sum(r[arm+'_unique'] for r in ambiguous),'remaining mean',statistics.mean(r[arm+'_classes'] for r in ambiguous),'lost truth',sum(r[arm+'_wrong'] for r in rows))

if __name__=='__main__':run()
