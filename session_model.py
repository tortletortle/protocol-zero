"""Offline, bounded-history session model. Missing transitions are unseen, not proven illegal."""
from collections import defaultdict
from protocol_spec import decode

START='@start'; END='@end'


def symbols(spec, bursts, offset):
    """Bursts are externally ordered (direction, complete application byte stream)."""
    if type(offset) is not int or offset<0:
        raise ValueError('invalid type offset')
    events=[]; unchecked=0
    for direction,data in bursts:
        if direction not in ('C','S'):
            raise ValueError('direction must be C or S')
        r=decode(spec,data)
        if len(r['alternatives'])!=1:
            return dict(status='unresolved_framing',events=[],unchecked=0)
        for frame in r['alternatives'][0]['frames']:
            f=bytes.fromhex(frame)
            if len(f)<=offset:
                return dict(status='missing_type_byte',events=[],unchecked=0)
            events.append('%s:%02x'%(direction,f[offset]))
            unchecked+=r['status']!='checksum_verified'
    return dict(status='ok' if events else 'empty',events=events,unchecked=unchecked)


def _check(seq):
    if not seq or any(not isinstance(e,str) or e in (START,END) for e in seq):
        raise ValueError('nonempty event sequences required; start/end are reserved')


def fit(sessions, depth=2):
    """depth=None is a full prefix tree; otherwise merge identical suffix histories."""
    if depth is not None and (type(depth) is not int or not 1<=depth<=8):
        raise ValueError('depth must be 1..8 or None')
    edges=defaultdict(set)
    for seq in sessions:
        _check(seq); history=(START,)
        for e in (*seq,END):
            edges[history].add(e)
            history=(*history,e) if depth is None else (*history,e)[-depth:]
    return dict(depth=depth,transitions=[dict(history=list(h),allowed=sorted(v)) for h,v in sorted(edges.items())])


def assess(model, seq):
    _check(seq); depth=model['depth']; history=(START,)
    edges={tuple(x['history']):set(x['allowed']) for x in model['transitions']}
    for i,e in enumerate((*seq,END)):
        if e not in edges.get(history,()):
            return dict(status='unseen_transition',position=i,history=list(history),event=e)
        history=(*history,e) if depth is None else (*history,e)[-depth:]
    return dict(status='consistent_with_model')


def choose(train, validation_positive, validation_negative=(), depths=(1,2,3)):
    """Hyperparameter selection on separate labeled validation sessions only."""
    if not train or not validation_positive:
        raise ValueError('training and positive validation required')
    candidates=[]
    for d in depths:
        m=fit(train,d)
        missing=sum(assess(m,s)['status']!='consistent_with_model' for s in validation_positive)
        false=sum(assess(m,s)['status']=='consistent_with_model' for s in validation_negative)
        # Balanced error when negative labels are available; never invent them.
        loss=missing/len(validation_positive)+(false/len(validation_negative) if validation_negative else 0)
        candidates.append((loss,len(m['transitions']),d,m))
    loss,_,d,m=min(candidates,key=lambda x:x[:3])
    return m,dict(depth=d,validation_loss=loss,negative_labels=bool(validation_negative))
