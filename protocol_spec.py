"""Versioned, conservative executable description of observed protocol candidates."""
import json
from pipeline import checksum
from evaluate_v08 import MODELS
from stream_framing import split


def export(result):
    groups=[]
    for c in result['groups']:
        groups.append(dict(selected=c in result['selected'], rules=[list(r) for r in c['rules']],
            checksums=c['checksums'], observed_constants=[[int(k),v] for k,v in sorted(c['constants'].items())],
            length_fields=c['length_fields']))
    return dict(version=1, source_status=result['status'], groups=groups)


def load(text):
    spec=json.loads(text)
    if not isinstance(spec,dict) or type(spec.get('version')) is not int or spec['version']!=1:
        raise ValueError('unsupported schema version')
    groups=spec.get('groups')
    if not isinstance(groups,list) or len(groups)>1320:
        raise ValueError('invalid groups')
    count=0
    for g in groups:
        if not isinstance(g,dict) or type(g.get('selected')) is not bool:
            raise ValueError('invalid group')
        rules=g.get('rules'); names=g.get('checksums'); constants=g.get('observed_constants')
        if not isinstance(rules,list) or not rules or not isinstance(names,list) or not isinstance(constants,list):
            raise ValueError('invalid evidence')
        count+=len(rules)
        if count>1320: raise ValueError('too many rules')
        for r in rules:
            if not isinstance(r,list) or len(r)!=4: raise ValueError('invalid rule')
            o,w,e,b=r
            if type(o) is not int or type(w) is not int or type(b) is not int or not 0<=o<8 or w not in (1,2,4) or e not in ('big','little') or not -16<=b<=16:
                raise ValueError('invalid rule')
        if any(not isinstance(n,str) or n not in ('SUM8','XOR8',*MODELS) for n in names): raise ValueError('unknown checksum')
        for c in constants:
            if not isinstance(c,list) or len(c)!=2 or any(type(x) is not int for x in c) or not 0<=c[0]<16 or not 0<=c[1]<256:
                raise ValueError('invalid constant')
    return spec


def decode(spec,data):
    """Evaluate selected hypotheses independently; observations are not hard constants."""
    if not data: return dict(status='empty_input', alternatives=[])
    if len(data)>2**20: return dict(status='input_limit', alternatives=[])
    options={}; framed=False
    for g in spec['groups']:
        if not g['selected']: continue
        for rule in g['rules']:
            frames=split(data,rule)
            if frames is None: continue
            framed=True
            names=[n for n in g['checksums'] if all(len(f)>=2 and checksum(f[:-1],n)==f[-1] for f in frames)]
            if g['checksums'] and not names: continue
            sig=tuple(map(len,frames))
            a=options.setdefault(sig,dict(frames=[f.hex() for f in frames], hypotheses=[]))
            a['hypotheses'].append(dict(rule=rule,checksums=names,
                constant_mismatches=sum(i>=len(f) or f[i]!=v for f in frames for i,v in g['observed_constants'])))
    alternatives=list(options.values())
    if not alternatives: status='checksum_rejected' if framed else 'no_framing'
    elif len(alternatives)>1: status='ambiguous_boundaries'
    elif all(h['checksums'] for h in alternatives[0]['hypotheses']): status='checksum_verified'
    else: status='unverified'
    return dict(status=status,alternatives=alternatives)
