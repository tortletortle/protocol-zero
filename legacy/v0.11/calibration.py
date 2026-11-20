import json, statistics, math, time
from joint import generate,fit,predict,observations
from benchmark import edges,select

def evidence(d,m):
 if m is None:return dict(n=0,coverage=0,match=0,diversity=0)
 h,o,e,l,t,a,b=m; es=list(edges(d,h,o,e)); p=observations(d,es,l,t)
 good=[ij for ij,(x,y) in zip(es,p) if (a*x+b)%256==y]; chosen=select(good,True)
 return dict(n=len(chosen),coverage=sum(j-i for i,j in chosen)/max(1,len(d)),match=len(good)/max(1,len(es)),diversity=len({y for x,y in p if (a*x+b)%256==y}))

def run():
 rows=[]
 for group in ('clean','noise','outside'):
  for seed in range(71000,71024):
   d,truth=generate(seed+1000*('clean','noise','outside').index(group),group); a=len(d)//3;b=2*len(d)//3
   m=fit(d[:a],'joint'); ev=evidence(d[a:b],m); actual={(i-b,j-b) for i,j in truth if i>=b}; pred=set(predict(d[b:],m)); f=2*len(pred&actual)/(len(pred)+len(actual)); accept=m is not None and ev['n']>=8 and ev['coverage']>=.65 and ev['diversity']>=4
   rows.append(dict(group=group,seed=seed,baseline=m is not None,accepted=accept,evidence=ev,raw_f1=f,gated_f1=f if accept else 0))
 summary={g:{k:statistics.mean(r[k] for r in rows if r['group']==g) for k in ('baseline','accepted','raw_f1','gated_f1')} for g in ('clean','noise','outside')};print(json.dumps(summary,indent=2));json.dump(dict(summary=summary,rows=rows),open('results_v07.json','w'),indent=2)
if __name__=='__main__':run()
