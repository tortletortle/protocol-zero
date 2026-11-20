"""Offline classic PCAP -> TCP payload records; no application decoding."""
import struct


def payloads(data, port=None):
    magic = data[:4]
    endian = {b'\xd4\xc3\xb2\xa1':'<', b'\xa1\xb2\xc3\xd4':'>', b'\x4d\x3c\xb2\xa1':'<', b'\xa1\xb2\x3c\x4d':'>'}.get(magic)
    if endian is None or len(data)<24:
        raise ValueError('classic PCAP required')
    if struct.unpack_from(endian+'I', data,20)[0]!=1:
        raise ValueError('Ethernet link type required')
    i=24
    while i<len(data):
        if i+16>len(data): raise ValueError('truncated record header')
        _,_,n,original=struct.unpack_from(endian+'IIII',data,i); i+=16
        if i+n>len(data): raise ValueError('truncated record')
        p=data[i:i+n]; i+=n
        if n!=original or len(p)<34 or p[12:14]!=b'\x08\x00': continue
        ip=p[14:]; ih=(ip[0]&15)*4; total=int.from_bytes(ip[2:4],'big')
        if ip[0]>>4!=4 or ih<20 or total>len(ip) or total<ih+20 or ip[9]!=6: continue
        if int.from_bytes(ip[6:8],'big')&0x3fff: continue
        tcp=ip[ih:total]; th=(tcp[12]>>4)*4
        if th<20 or th>len(tcp): continue
        src,dst=struct.unpack_from('!HH',tcp)
        if port is not None and port not in (src,dst): continue
        body=tcp[th:]
        if body: yield body
