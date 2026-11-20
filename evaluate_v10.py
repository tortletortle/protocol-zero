import random,json
from ambiguity import hypotheses,update
from collections import defaultdict

def run():
 rows=[]
 for kind in ('byte_random','byte_constant','little','big','little32','outside'):
  for seed in range(100):
   r=random.Random(105000+seed); w,e={'byte_random':(1,'little'),'byte_constant':(1,'little'),'little':(2,'little'),'big':(2,'big'),'little32':(4,'little'),'outside':(2,'little')}[kind];start=r.randrange(10,40)
   data=[]
   for j in range(300):
    x=((start+j*(3 if kind=='outside' else 1))%(256**w)).to_bytes(w,e)
    data.append(x+(b'\x00'*4 if kind=='byte_constant' else r.randbytes(4)))
   truth=None if kind=='outside' else (w,e)
   initial=hypotheses(data[:30]); c=initial[:]; resolved_at=None
   for j in range(30,len(data)):
    c=update(c,data[j-1],data[j]);
    if len(c)==1 and resolved_at is None:resolved_at=j+1
   # forced selection baseline, smallest fitting candidate
   forced=min(initial) if initial else None
   rows.append(dict(kind=kind,seed=seed,truth=truth,initial=initial,final=c,forced_correct=forced==truth,initial_retains=truth in initial if truth else not initial,final_retains=truth in c if truth else not c,ambiguous=len(c)>1,unique_correct=len(c)==1 and c[0]==truth,wrong_unique=len(c)==1 and c[0]!=truth,rejected=not c,resolved_at=resolved_at))
 summary={k:{m:sum(row[m] for row in rows if row['kind']==k) for m in ('forced_correct','initial_retains','final_retains','ambiguous','unique_correct','wrong_unique','rejected')} for k in dict.fromkeys(r['kind'] for r in rows)}
 print(json.dumps(summary,indent=2));json.dump(dict(summary=summary,rows=rows),open('results_v10.json','w'),indent=2)
if __name__=='__main__':run()
