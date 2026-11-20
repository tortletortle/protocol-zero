import random,json
from dependency import infer
from collections import defaultdict

def run():
 rows=[]
 for kind in ('u8_random','u8_constant','u16_carry','u16_no_carry','u32_partial','u32_double_carry','u16_big','coupled_bytes','step3'):
  for seed in range(100):
   r=random.Random(761000+seed); w=4 if kind.startswith('u32') else 1 if kind.startswith('u8') else 2; e='big' if kind=='u16_big' else 'little'; start=65500 if kind=='u32_double_carry' else 240 if kind!='u16_no_carry' else 10; start+=r.randrange(10); n=40
   def record(j):
    x=(start+j*(3 if kind=='step3' else 1))%(256**w)
    return x.to_bytes(w,e)+(b'\x00'*3 if kind=='u8_constant' else r.randbytes(3))
   data=[record(j) for j in range(n)]
   # coupled_bytes is observationally identical to a 16-bit word but has two logical fields.
   truth=(w,e) if kind not in ('step3','coupled_bytes') else None
   ranked=infer(data); top=(ranked[0]['width'],ranked[0]['endian']) if ranked else None
   forced=min(((x['width'],x['endian']) for x in ranked),default=None)
   rows.append(dict(kind=kind,seed=seed,truth=truth,ranked=ranked,top_correct=top==truth,shortest_correct=forced==truth,ambiguous=len(ranked)>1,rejected=not ranked,carry_supported=bool(ranked and ranked[0]['score'])))
 summary={k:{m:sum(x[m] for x in rows if x['kind']==k) for m in ('top_correct','shortest_correct','ambiguous','rejected','carry_supported')} for k in dict.fromkeys(x['kind'] for x in rows)}
 print(json.dumps(summary,indent=2));json.dump(dict(summary=summary,rows=rows),open('results_v11.json','w'),indent=2)
if __name__=='__main__':run()
