"""Offline directional TCP reassembly, bounded; no connection epoch detection."""
import struct
from collections import defaultdict


def segments(data, port=None):
    endian={bytes.fromhex(k):v for k,v in [('d4c3b2a1','<'),('a1b2c3d4','>'),('4d3cb2a1','<'),('a1b23c4d','>')]}.get(data[:4])
    if endian is None or len(data)<24 or struct.unpack_from(endian+'I',data,20)[0]!=1:
        raise ValueError('classic Ethernet PCAP required')
    i=24
    while i<len(data):
        if i+16>len(data): raise ValueError('truncated record header')
        _,_,n,original=struct.unpack_from(endian+'IIII',data,i); i+=16
        if i+n>len(data): raise ValueError('truncated record')
        p=data[i:i+n]; i+=n
        if n!=original or len(p)<34 or p[12:14]!=bytes.fromhex('0800'): continue
        ip=p[14:]; ih=(ip[0]&15)*4; total=int.from_bytes(ip[2:4],'big')
        if ip[0]>>4!=4 or ih<20 or total>len(ip) or total<ih+20 or ip[9]!=6: continue
        if int.from_bytes(ip[6:8],'big')&0x3fff: continue
        tcp=ip[ih:total]; th=(tcp[12]>>4)*4
        if th<20 or th>len(tcp): continue
        src,dst,seq=struct.unpack_from('!HHI',tcp)
        if port is not None and port not in (src,dst): continue
        syn=bool(tcp[13]&2); body=tcp[th:]
        if body or syn: yield ((ip[12:16],src,ip[16:20],dst),(seq+syn)%2**32,body,syn)


def assemble(parts, limit=2**20):
    parts=list(parts)
    if not parts: return {'status':'empty','data':b''}
    starts={s for s,b,syn in parts if syn}
    if len(starts)>1: return {'status':'multiple_syn','data':b''}
    anchor=next(iter(starts)) if starts else parts[0][0]
    coords=[((s-anchor+2**31)%2**32-2**31,b) for s,b,_ in parts if b]
    if not coords: return {'status':'empty','data':b''}
    lo=0 if starts else min(s for s,b in coords); hi=max(s+len(b) for s,b in coords)
    if min(s for s,b in coords)<lo: return {'status':'before_syn','data':b''}
    if hi-lo>limit: return {'status':'span_limit','data':b''}
    buf=bytearray(hi-lo); seen=bytearray(hi-lo); duplicates=0
    for s,body in coords:
        for j,v in enumerate(body,s-lo):
            if seen[j]:
                if buf[j]!=v: return {'status':'conflict','data':b''}
                duplicates+=1
            buf[j]=v; seen[j]=1
    missing=seen.count(0)
    if missing: return {'status':'gap','data':b'','missing':missing}
    return {'status':'ok','data':bytes(buf),'duplicates':duplicates,'syn_observed':bool(starts)}


def streams(data,port=None):
    grouped=defaultdict(list)
    for key,s,b,syn in segments(data,port): grouped[key].append((s,b,syn))
    return {key:assemble(parts) for key,parts in grouped.items()}
