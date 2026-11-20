"""Infer a JSON candidate description and decode an offline binary stream."""
import argparse
import json
from pathlib import Path
from pipeline import analyze, analyze_pcaps
from protocol_spec import export, load, decode


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('infer'); a.add_argument('train'); a.add_argument('validation'); a.add_argument('output'); a.add_argument('--pcap',action='store_true'); a.add_argument('--port',type=int)
    b=sub.add_parser('decode'); b.add_argument('spec'); b.add_argument('stream')
    args=p.parse_args()
    if args.action=='infer':
        train=[Path(args.train).read_bytes()]; validation=[Path(args.validation).read_bytes()]
        result=analyze_pcaps(train,validation,args.port) if args.pcap else analyze(train,validation)
        Path(args.output).write_text(json.dumps(export(result),indent=2)+'\n',encoding='utf-8')
        print(result['status'])
    else:
        print(json.dumps(decode(load(Path(args.spec).read_text(encoding='utf-8')),Path(args.stream).read_bytes()),indent=2))

if __name__=='__main__': main()
