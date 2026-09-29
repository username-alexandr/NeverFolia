#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,queue,shutil,subprocess,threading,time,zipfile

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.work/r3924-ice-target'
OUT=ROOT/'artifacts-r3924-ice-target'

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def one(root,pattern):
    hits=list(Path(root).rglob(pattern));need(len(hits)==1,f'{pattern}: {hits}');return hits[0]

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False)
    core=one(ROOT/'core-input','NeverFolia-*.jar')
    ow=one(ROOT/'ow-input','NeverOverworld-R3924-Effective.zip')
    nn=one(ROOT/'nn-input','NeverNether.zip')
    libs=WORK/'libs';classes=WORK/'classes';libs.mkdir();classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,name in enumerate(z.namelist()):
            if name.endswith('.jar') and name.startswith(('META-INF/versions/','META-INF/libraries/')):
                (libs/f'{i}-{Path(name).name}').write_bytes(z.read(name))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    need(cp,'empty classpath')
    src=ROOT/'qa/field-r3924/R3924IceTargetQa.java'
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(src)],text=True,capture_output=True)
    (OUT/'javac.log').write_text(p.stdout+p.stderr);need(p.returncode==0,'plugin compile failed')
    plugin=WORK/'R3924IceTargetQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3924IceTargetQa\nversion: '1'\nmain: R3924IceTargetQa\napi-version: '26.2'\nfolia-supported: true\n")
    srv=WORK/'server';packs=srv/'world/datapacks';packs.mkdir(parents=True);(srv/'plugins').mkdir()
    shutil.copyfile(ow,packs/'NeverOverworld.zip');shutil.copyfile(nn,packs/'NeverNether.zip');shutil.copyfile(plugin,srv/'plugins/R3924IceTargetQa.jar')
    (srv/'eula.txt').write_text('eula=true\n')
    (srv/'server.properties').write_text(
      'level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
      'server-ip=127.0.0.1\nserver-port=25624\nonline-mode=false\nenforce-secure-profile=false\n'
      'enable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\n'
      'spawn-protection=0\npause-when-empty-seconds=-1\n')
    proof=OUT/'proof';ice=OUT/'ice';proof.mkdir();ice.mkdir()
    cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G',
         '-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true',
         '-Dneverfolia.r399ReportDirectory='+str(proof.resolve()),
         '-Dneverfolia.r3913IceReport='+str(ice.resolve()),
         '-jar',str(core.resolve()),'--nogui']
    log=OUT/'server.log'
    with log.open('w') as out:
        proc=subprocess.Popen(cmd,cwd=srv,stdin=subprocess.PIPE,stdout=out,stderr=subprocess.STDOUT,text=True)
        try: code=proc.wait(timeout=360)
        except subprocess.TimeoutExpired:
            proc.stdin.write('stop\n');proc.stdin.flush()
            try:code=proc.wait(timeout=60)
            except subprocess.TimeoutExpired:proc.kill();code=proc.wait()
            raise ValueError('server timeout')
    result=srv/'plugins/R3924IceTargetQa/result.json';need(code==0,'server exit '+str(code));need(result.is_file(),'plugin result missing')
    result_doc=json.loads(result.read_text());need(result_doc.get('pass') is True,'plugin failed')
    diag=ice/'target_component_-189_-223.json';need(diag.is_file(),'target component diagnostic missing')
    diag_doc=json.loads(diag.read_text())
    summary={'pass':True,'core_sha256':sha(core),'overworld_sha256':sha(ow),'nether_sha256':sha(nn),
             'observed':result_doc,'component':diag_doc}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R3924_ICE_TARGET '+json.dumps(summary))

if __name__=='__main__':main()
