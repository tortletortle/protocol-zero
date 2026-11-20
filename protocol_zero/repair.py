"""Conditional single-edit reconstruction; never promotes repaired data to trusted frames.
Assumptions: one intervening frame, intact header and checksum trailer, at most
one inserted/deleted byte or one flipped bit in payload, no gap padding.
"""
from dataclasses import dataclass, asdict
from functools import lru_cache
from .checksums import checksum, CHECKSUMS
from .model import FrameModel
from .framing import decode_stream

CRC_PARAMS = {'crc8_smbus':(7,0,0), 'crc8_j1850':(29,255,255), 'crc8_autosar':(47,255,255)}

@lru_cache(maxsize=3)
def _tables(poly):
    table=[]
    for x in range(256):
        for _ in range(8): x=((x<<1) ^ (poly if x&128 else 0))&255
        table.append(x)
    inv=[0]*256
    for i,x in enumerate(table): inv[x]=i
    assert len(set(table))==256
    return tuple(table),tuple(inv)

def _states(body, target, name):
    """Forward state at each boundary and required state before each suffix."""
    if name in CRC_PARAMS:
        p,init,xorout=CRC_PARAMS[name]; tab,inv=_tables(p)
        step=lambda s,b:tab[s^b]; back=lambda s,b:inv[s]^b
        solve=lambda s,t:s^inv[t]; target ^= xorout
    elif name=='sum8':
        init=0;step=lambda s,b:(s+b)&255;back=lambda s,b:(s-b)&255;solve=lambda s,t:(t-s)&255
    elif name=='xor8':
        init=0;step=lambda s,b:s^b;back=step;solve=step
    else: raise ValueError('unsupported checksum')
    f=[init]; r=[0]*(len(body)+1);r[-1]=target
    for b in body:f.append(step(f[-1],b))
    for i in range(len(body)-1,-1,-1):r[i]=back(r[i+1],body[i])
    return f,r,solve

def candidates(observed:bytes, model:FrameModel):
    """All distinct reconstructions in the bounded edit model, sorted lexically.
    O(n) checksum-state operations, O(n²) worst-case materialized bytes.
    """
    if model.trailer_size!=1 or model.checksum not in CHECKSUMS: return 'unsupported',[]
    if not observed.startswith(model.sync) or len(observed)<model.payload_offset+1: return 'invalid_header',[]
    p=model.payload_offset; lo=model.length_offset; hi=lo+model.length_width
    if not (len(model.sync)<=lo<hi<=p): return 'invalid_header',[]
    n=int.from_bytes(observed[lo:hi],model.length_endian)
    if n>model.max_payload: return 'invalid_length',[]
    delta=len(observed)-(p+n+1)
    if delta not in (-1,0,1): return 'outside_edit_budget',[]
    body=observed[:-1]; trailer=observed[-1:]; target=trailer[0]
    if delta==0 and checksum(body,model.checksum)==target: return 'already_valid',[]
    f,r,solve=_states(body,target,model.checksum); out=set()
    if delta==-1:
        kind='missing_byte'
        for i in range(p,len(body)+1):
            b=solve(f[i],r[i]);out.add(body[:i]+bytes([b])+body[i:]+trailer)
    elif delta==1:
        kind='extra_byte'
        for i in range(p,len(body)):
            if f[i]==r[i+1]:out.add(body[:i]+body[i+1:]+trailer)
    else:
        kind='bit_flip'
        for i in range(p,len(body)):
            b=solve(f[i],r[i+1]);v=b^body[i]
            if v and v&(v-1)==0:out.add(body[:i]+bytes([b])+body[i+1:]+trailer)
    return kind,sorted(out)

@dataclass(frozen=True)
class Profile:
    length:int
    constants:tuple[tuple[int,int],...]
    train_n:int
    validation_n:int
    def matches(self,payload):
        return len(payload)==self.length and all(payload[i]==v for i,v in self.constants)

def learn_profiles(train, validation, model, min_samples=12):
    """Conservative length-conditioned invariants, discovered on train only,
    retained only when all independent validation examples agree. Empirical,
    not hard protocol guarantees. Only original checksum-valid frames used.
    """
    def groups(streams):
        g={}
        for d in streams:
            for f in decode_stream(d,model)['frames']:
                payload=f.data[model.payload_offset:-model.trailer_size]
                g.setdefault(len(payload),[]).append(payload)
        return g
    a,b=groups(train),groups(validation);out={}
    for n,rows in a.items():
        val=b.get(n,[])
        if min(len(rows),len(val))<min_samples:continue
        constants=tuple((i,rows[0][i]) for i in range(n) if all(x[i]==rows[0][i] for x in rows) and all(x[i]==rows[0][i] for x in val))
        if constants:out[n]=Profile(n,constants,len(rows),len(val))
    return out

def repair_stream(data,model,profiles=None,stream_id=0,decoded=None):
    """Retain the original valid/suspect channels; add a separate hypothesis log.
    All candidates and empirical filtering are exposed; no auto-commit.
    """
    profiles=profiles or {}; decoded=decoded if decoded is not None else decode_stream(data,model,stream_id)
    frames=sorted(decoded['frames'],key=lambda x:x.start); repairs=[]
    for left,right in zip(frames,frames[1:]):
        a,b=left.end,right.start
        if b<=a:continue
        gap=data[a:b]
        if len(gap)>model.payload_offset+model.max_payload+model.trailer_size+1:continue
        kind,raw=candidates(gap,model)
        if kind in ('invalid_header','invalid_length','outside_edit_budget','unsupported','already_valid'):continue
        n=int.from_bytes(gap[model.length_offset:model.length_offset+model.length_width],model.length_endian)
        profile=profiles.get(n)
        filtered=[x for x in raw if profile is None or profile.matches(x[model.payload_offset:-1])]
        status=('no_candidate' if not raw else 'profile_conflict' if not filtered else 'ambiguous' if len(filtered)>1 else 'unique_under_profile' if profile is not None and len(raw)>1 else 'unique_under_edit_model')
        # Competing explanation: the payload is intact and only a bit in
        # the observed trailer changed. Do not force a payload edit.
        trailer_alternative = None
        if kind == 'bit_flip':
            expected = checksum(gap[:-1], model.checksum)
            difference = expected ^ gap[-1]
            if difference and difference & (difference-1) == 0:
                trailer_alternative = gap[:-1] + bytes([expected])
        expanded = sorted(set(raw + ([trailer_alternative] if trailer_alternative is not None else [])))
        expanded_filtered = [x for x in expanded if profile is None or profile.matches(x[model.payload_offset:-1])]
        expanded_status = ('no_candidate' if not expanded else 'profile_conflict' if not expanded_filtered else 'ambiguous' if len(expanded_filtered)>1 else 'unique_under_profile' if len(expanded)>1 else 'unique_under_edit_model')
        repairs.append({'stream_id':stream_id,'start':a,'end':b,'observed_hex':gap.hex(),'edit_kind':kind,'status':expanded_status,'payload_only_status':status,'raw_count':len(raw),'filtered_count':len(filtered),'raw_candidates_hex':[x.hex() for x in raw],'candidates_hex':[x.hex() for x in filtered],'profile':asdict(profile) if profile else None,'payload_only_proposed_hex':filtered[0].hex() if len(filtered)==1 else None,'trailer_flip_candidate_hex':trailer_alternative.hex() if trailer_alternative is not None else None,'expanded_count':len(expanded),'expanded_candidates_hex':[x.hex() for x in expanded],'expanded_filtered_hex':[x.hex() for x in expanded_filtered],'expanded_status':expanded_status,'proposed_hex':expanded_filtered[0].hex() if len(expanded_filtered)==1 else None,'trusted':False,'assumptions':['single frame between valid anchors','no gap padding','intact header','single payload edit with intact trailer OR single trailer bit flip','empirical profile may drift']})
    return repairs
