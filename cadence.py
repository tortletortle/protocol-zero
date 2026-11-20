"""Training-only cadence screening; diagnostics are not proof of exchangeability."""
from collections import Counter
from math import gcd, sqrt
from functools import reduce
from temporal import infer as block_infer


def diagnose(rows, max_block=32):
    if len(rows)<32 or not rows or len({len(r) for r in rows})!=1:
        return dict(status='insufficient_or_ragged')
    changes=[i for i in range(1,len(rows)) if rows[i]!=rows[i-1]]
    if len(changes)<16:
        return dict(status='insufficient_changes')
    size=reduce(gcd,changes)
    if size>max_block or len(rows)%size:
        return dict(status='unsupported_alignment',block_size=size)
    collapsed=rows[::size]; n=len(collapsed)
    if n<32:
        return dict(status='insufficient_blocks',block_size=size)
    # Categorical repeat-match ACF and numeric ACF on block representatives.
    peak=0.0
    for col in zip(*collapsed):
        mean=sum(col)/n; var=sum((x-mean)**2 for x in col)
        if not var: continue
        base=sum(c*(c-1) for c in Counter(col).values())/(n*(n-1))
        for k in range(1,min(8,n//4)+1):
            num=sum((a-mean)*(b-mean) for a,b in zip(col,col[k:]))/var
            match=sum(a==b for a,b in zip(col,col[k:]))/(n-k)
            cat=(match-base)/(1-base)
            peak=max(peak,abs(num),abs(cat))
    threshold=max(.25,3.5/sqrt(n))
    return dict(status='unresolved_dependence' if peak>threshold else 'candidate',
                block_size=size, blocks=n, peak_acf=peak, screening_threshold=threshold)


def infer(train, validation, *, permutations=199, seed=0, alpha=.05):
    d=diagnose(train)
    if d['status']!='candidate':
        return dict(status=d['status'],diagnostic=d,edges=[])
    b=d['block_size']
    if not validation or len(validation)%b or any(len(r)!=len(train[0]) for r in validation):
        return dict(status='unsupported_validation',diagnostic=d,edges=[])
    # Alignment check uses within-series structure, not rule agreement.
    if any(validation[i]!=validation[i-1] for i in range(1,len(validation)) if i%b):
        return dict(status='cadence_mismatch',diagnostic=d,edges=[])
    r=block_infer(train,validation,b,alpha=alpha,permutations=permutations,seed=seed)
    return dict(status=r['status'],diagnostic=d,edges=r['edges'],
                evidence='exploratory_assumes_exchangeable_aligned_blocks')
