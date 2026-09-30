#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,shutil,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'.work/r3925-seam';OUT=ROOT/'artifacts-r3925-seam'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def exact(root,name,digest):
    hits=[p for p in Path(root).rglob(name) if p.is_file() and sha(p)==digest]
    need(len(hits)==1,f'{name}: {hits}');return hits[0]
def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    core=exact(ROOT/'core-input',os.environ['R3925_CORE_NAME'],os.environ['R3925_CORE_SHA'])
    ow=exact(ROOT/'ow-input','NeverOverworld-R3925-NativeSea.zip',os.environ['R3925_OW_SHA'])
    nn=exact(ROOT/'nn-input','NeverNether.zip',os.environ['R3925_NN_SHA'])
    libs=WORK/'libs';classes=WORK/'classes';libs.mkdir();classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):
                (libs/f'{i}-{Path(n).name}').write_bytes(z.read(n))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')));need(cp,'empty classpath')
    src=ROOT/'qa/field-r3925/R3925SeamQa.java'
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(src)],text=True,capture_output=True)
    (OUT/'javac.log').write_text(p.stdout+p.stderr);need(p.returncode==0,'compile failed')
    plugin=WORK/'R3925SeamQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3925SeamQa\nversion: '3925'\nmain: R3925SeamQa\napi-version: '26.2'\nfolia-supported: true\n")
    srv=WORK/'server';(srv/'world/datapacks').mkdir(parents=True);(srv/'plugins').mkdir()
    shutil.copyfile(ow,srv/'world/datapacks/NeverOverworld.zip');shutil.copyfile(nn,srv/'world/datapacks/NeverNether.zip');shutil.copyfile(plugin,srv/'plugins/R3925SeamQa.jar')
    (srv/'eula.txt').write_text('eula=true\n')
    (srv/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25626\nonline-mode=false\nenforce-secure-profile=false\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nmax-tick-time=-1\n')
    log=OUT/'server.log'
    with log.open('w') as out:
        proc=subprocess.Popen(['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-jar',str(core.resolve()),'--nogui'],cwd=srv,stdin=subprocess.PIPE,stdout=out,stderr=subprocess.STDOUT,text=True)
        try:code=proc.wait(timeout=420)
        except subprocess.TimeoutExpired:
            try:proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=60)
            except Exception:proc.kill();code=proc.wait()
            raise ValueError('timeout')
    result=srv/'plugins/R3925SeamQa/result.json';need(code==0,'exit '+str(code));need(result.is_file(),'result missing')
    doc=json.loads(result.read_text());need(doc.get('pass') is True,'plugin fail '+repr(doc.get('error')))
    rows=doc['rows'];actual=max(r['actual_delta'] for r in rows);base=max(r['base_delta'] for r in rows)
    summary={'pass':True,'actual_max_delta':actual,'base_max_delta':base,'rows':rows}
    (OUT/'result.json').write_text(json.dumps(doc,indent=2)+'\n');(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R3925_SEAM '+json.dumps({'actual_max_delta':actual,'base_max_delta':base}),flush=True)
if __name__=='__main__':main()
