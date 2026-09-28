#!/usr/bin/env python3
"""Internal resource repair checkpoint. Never installs into an existing world."""
from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'resource-evidence';OUT.mkdir(exist_ok=True)
BASE='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
PACK='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def find(name,want):
    p=[p for p in (ROOT/'baseline').rglob(name) if p.is_file() and sha(p)==want]
    need(len(p)==1,'Missing exact input '+name);return p[0]
def main():
    report={'pass':False,'production_accepted':False,'gameplay_tested':False,'commit':os.getenv('GITHUB_SHA')}
    try:
        jar=find('server.jar',BASE);pack=find('NeverOverworld.zip',PACK)
        audit=load('r3914_audit',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
        builder=load('r3914_carts',ROOT/'qa/field-r394/build_candidate.py')
        tests=subprocess.run([sys.executable,str(ROOT/'qa/field-r394/build_candidate.py'),'--self-test'],capture_output=True,text=True,timeout=60)
        (OUT/'builder-tests.log').write_text(tests.stdout+tests.stderr)
        print(tests.stdout+tests.stderr,flush=True);need(tests.returncode==0,'Builder unit tests failed')
        before=audit.audit_files(jar,pack);need(not before['errors'],'Input graph could not be parsed')
        (OUT/'resource-before.json').write_text(json.dumps(before,indent=2)+'\n')
        dest=ROOT/'internal-resource-candidate';dest.mkdir(exist_ok=False)
        candidate=dest/'NeverOverworld.zip'
        built=builder.build(pack,candidate)
        (OUT/'cart-build.json').write_text(json.dumps(built,indent=2)+'\n')
        after=audit.audit_files(jar,candidate);need(not after['errors'],'Output graph could not be parsed')
        (OUT/'resource-after.json').write_text(json.dumps(after,indent=2)+'\n')
        missing=lambda r:{(v['kind'],v['id']) for v in r['missing']}
        left,right=missing(before),missing(after)
        expected={('template','nova_structures:tavern/tavern_event_trader_car_'+r+'_'+b) for r in builder.RECOVER for b in builder.BIOMES}
        need(left-right==expected and not right-left,'Unexpected graph changes')
        need(before['counts']['roots']==after['counts']['roots'],'Root structure set changed')
        need(sha(pack)==PACK and sha(jar)==BASE,'Input changed')
        report.update({'pass':True,'source_pack_sha256':PACK,'candidate_pack_sha256':sha(candidate),
                       'restored_templates':len(expected),'remaining_missing':len(right),
                       'matched_reference_variants':len(built['validated_existing_variants']),
                       'runtime_tested':False,'missing_before':before['counts'],'missing_after':after['counts']})
        (dest/'NOT-A-USER-RELEASE.txt').write_text('Internal cart reconstruction checkpoint; 73 other missing templates and gameplay acceptance remain.\n')
        for n in ('cart-build.json','resource-before.json','resource-after.json'):
            (dest/n).write_bytes((OUT/n).read_bytes())
    except BaseException as e:
        report['error']=repr(e)
        raise
    finally:
        (OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print('RESOURCE_REPAIR_SUMMARY',json.dumps(report),flush=True)
if __name__=='__main__':main()
