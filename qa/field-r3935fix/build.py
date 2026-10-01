#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil,subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';CAND=ROOT/'candidate';BASE=ROOT/'baseline-r3934'

BASE_CORE='d84650ac22746d51f6b530af4407a851695da577cb18a6baf9500064f11d609f'
BASE_PACK='946cd27c26800271ed976665a60b7d4f602d3b552e5abdcb7d7bcbeb331bda25'
NETHER='5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'

def need(v,m):
    if not v:raise ValueError(m)

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run(args,name,timeout=300):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
    (OUT/name).write_text(p.stdout);print(p.stdout,flush=True);need(p.returncode==0,'failed '+name)

def main():
    OUT.mkdir(exist_ok=True);CAND.mkdir(exist_ok=True)
    server=BASE/'server.jar'
    pack=BASE/'world/datapacks/NeverOverworld.zip'
    nether=BASE/'world/datapacks/NeverNether.zip'
    need(server.is_file() and pack.is_file() and nether.is_file(),'R39.34 baseline incomplete')
    need(sha(server)==BASE_CORE,'wrong R39.34 server')
    need(sha(pack)==BASE_PACK,'wrong R39.34 NeverOverworld')
    need(sha(nether)==NETHER,'wrong NeverNether')

    shutil.copyfile(server,CAND/'server.jar')
    shutil.copyfile(nether,CAND/'NeverNether.zip')
    run([
      'python3',str(ROOT/'qa/field-r3935fix/patch_pack.py'),
      str(pack),str(CAND/'NeverOverworld.zip')
    ],'r3935-pack.log',timeout=420)

    report={
      'build_pass':True,
      'base_r3934_core_sha256':BASE_CORE,
      'candidate_core_sha256':sha(CAND/'server.jar'),
      'base_r3934_pack_sha256':BASE_PACK,
      'candidate_pack_sha256':sha(CAND/'NeverOverworld.zip'),
      'nether_sha256':NETHER,
      'kernel_changed':False,
      'ocean_pillar_waystone_children_disabled':True,
      'expected_ocean_pillar_piece_count':1,
      'production_accepted':False
    }
    (OUT/'build-r3935.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R3935_BUILD '+json.dumps(report),flush=True)

if __name__=='__main__':main()
