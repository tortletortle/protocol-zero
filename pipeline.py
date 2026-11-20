"""Offline evidence pipeline. Exact checksums are evidence, not protocol identity."""
from stream_reassembly import streams
from stream_framing import infer, split
from length_rules import infer as lengths
from evaluate_v08 import MODELS, check


def checks(rows):
    if min(map(len, rows)) < 2 or len({r[-1] for r in rows}) < 8:
        return []
    return [name for name in ['SUM8','XOR8',*MODELS]
            if all(checksum(r[:-1],name)==r[-1] for r in rows)]


def checksum(data,name):
    if name=='SUM8': return sum(data)%256
    if name=='XOR8':
        value=0
        for x in data: value^=x
        return value
    return check(data,name)


def analyze(train, validation):
    rules=infer(train,validation)
    groups={}
    for rule in rules:
        parts=[split(d,rule) for d in train+validation]
        signature=tuple(tuple(map(len,p)) for p in parts)
        groups.setdefault(signature,[]).append(rule)
    candidates=[]
    for signature, rs in groups.items():
        p=[f for d in train for f in split(d,rs[0])]
        q=[f for d in validation for f in split(d,rs[0])]
        confirmed=sorted(set(checks(p)) & set(checks(q)))
        constants={i:p[0][i] for i in range(min(16,min(map(len,p+q))))
                   if all(f[i]==p[0][i] for f in p+q)}
        candidates.append(dict(rules=rs, boundaries=signature, checksums=confirmed,
                               constants=constants, length_fields=lengths(p,q)['rules']))
    supported=[c for c in candidates if c['checksums']]
    selected=supported or candidates
    status='no_candidate' if not selected else 'checksum_supported' if len(selected)==1 and supported else 'boundary_only' if len(selected)==1 else 'ambiguous'
    return dict(status=status, raw_rules=len(rules), groups=candidates, selected=selected)


def analyze_pcaps(train,validation,port=None):
    def unpack(caps):
        out=[]
        for data in caps:
            found=[r for r in streams(data,port).values() if r['status']!='empty']
            if len(found)!=1 or found[0]['status']!='ok' or not found[0]['syn_observed']:
                return None
            out.append(found[0]['data'])
        return out
    p,q=unpack(train),unpack(validation)
    if not p or not q: return dict(status='unsupported_stream',raw_rules=0,groups=[],selected=[])
    return analyze(p,q)
