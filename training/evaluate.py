"""Evaluate a checkpoint on caller-supplied frozen JSONL; aggregate output only."""
import argparse,json,shutil,tempfile
from pathlib import Path
from model import predict_laya,softmax
from metrics import groups
from config import read

def main():
 p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--data',required=True);p.add_argument('--temperature',type=float,required=True);p.add_argument('--device',default='cuda:0');p.add_argument('--output',required=True);a=p.parse_args()
 from laya.train import load_checkpoint
 with tempfile.TemporaryDirectory() as d:
  shutil.copytree(a.checkpoint,Path(d)/'model');model,tok,_=load_checkpoint(str(Path(d)/'model'));model.to(a.device).eval();rows=read(a.data);z,lat,counts=predict_laya(model,tok,rows,a.device)
  Path(a.output).write_text(json.dumps({'metrics':groups(rows,softmax(z/a.temperature),.5),'latency_ms':lat,'windows':sum(counts)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
