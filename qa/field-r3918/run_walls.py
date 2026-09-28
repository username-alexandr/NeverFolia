#!/usr/bin/env python3
from pathlib import Path
import json,os,shutil,subprocess,zipfile
import restore_stray_walls as fix
import run_mansion as r
s=fix.s;ROOT=fix.ROOT;OUT=r.OUT;WORK=ROOT/'.work/r3918-walls'

def compile_plugin(core,cases):
    libs=WORK/'libs';classes=WORK/'classes';libs.mkdir();classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    source=Path(__file__).with_name('R3918WallsQa.java')
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(source)],capture_output=True,text=True,timeout=120)
    (OUT/'walls-qa-javac.log').write_text(p.stdout+p.stderr);s.need(p.returncode==0,'QA compile failed: '+p.stderr)
    target=WORK/'WallsQa.jar'
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
        # Reuse the completed resource phase reader and its strict nine base checks.
        z.writestr('plugin.yml',"name: R3918ResourceQa\nversion: 'walls-1'\nmain: R3918WallsQa\napi-version: '26.2'\nfolia-supported: true\n")
        z.writestr('wall-cases.json',json.dumps(cases))
    return target

def validate(phase,cases):
    s.need(phase.get('pass') is True and phase.get('exit_code')==0,'Actual wall process failed')
    rows=phase['observed'].get('wall_checks',[])
    s.need(len(rows)==36 and [x['id'] for x in rows]==[x['id'] for x in cases],'Missing or duplicate restored model coverage')
    for actual,want in zip(rows,cases):
        s.need(actual.get('pass') is True and actual.get('size')==want['size'] and actual.get('placed_nonair')==want['nonair'] and actual.get('loaded_jigsaws')==want['jigsaw_count'],'Incorrect observed wall geometry')

def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(parents=True,exist_ok=False);report={'pass':False,'all_reported_bugs_fixed':False,'production_accepted':False,'user_kit_published':False}
    try:
        base=r.exact(ROOT/'integrated-input','NeverOverworld-R3915-Combined.zip',fix.fix.BASE)
        core=r.exact(ROOT/'swift-input','server-r3915.jar',fix.fix.CORE)
        nether=r.exact(ROOT/'inputs','NeverNether.zip',r.NETHER)
        before=json.loads(r.one(ROOT/'integrated-input','combined-resource-after.json').read_text())
        payload,build=fix.build(base.read_bytes(),fix.author_bytes(),before,fix.author_v6_bytes())
        target=OUT/'NeverOverworld-R3918-Walls.zip'
        with target.open('xb') as f:f.write(payload)
        r.save('walls-build.json',build);report['build']=build
        finalfiles=s.read_zip(payload);nf=s.read_zip(nether.read_bytes())
        restored_paths=(*fix.fix.POOLS,fix.EVENT_POOL,*build.get('proven_dangling_repair',{}).get('pools',{}),
                        *(m['path'] for m in build['models']),*(m['path'] for m in build.get('closure_models',[])),
                        *(m['path'] for m in build.get('future_models',[])))
        s.need(all(p not in nf or nf[p]==finalfiles[p] for p in restored_paths),'Nether shadows a restored resource')
        audit=s.load('r3918_walls_audit',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
        after=audit.audit_files(core,target);r.save('walls-resource-after.json',after)
        a={(x['kind'],x['id']) for x in before['missing']};b={(x['kind'],x['id']) for x in after['missing']}
        expected={('template',m['id']) for m in build['models']}|{('template',m['id']) for m in build.get('future_models',[])}|{('template',x) for x in build.get('proven_dangling_repair',{}).get('targets',[])}|{('template','minecraft:minecraft/empty')}
        report['resource_delta']={'before':before['counts'],'after':after['counts'],'removed':sorted(a-b),'introduced':sorted(b-a),'errors':after['errors'],'full_resource_acceptance':after['pass']}
        r.save('walls-resource-delta.json',report['resource_delta']);print('R3918_WALL_RESOURCE_DELTA',json.dumps(report['resource_delta']),flush=True)
        s.need(not after['errors'] and a-b==expected and not b-a,'New unresolved dependencies or incomplete restoration')
        s.need({x['id'] for x in before['roots']}=={x['id'] for x in after['roots']},'Root coverage changed')
        plugin=compile_plugin(core,build['models']);folder=WORK/'server';packs=folder/'world/datapacks';packs.mkdir(parents=True);(folder/'plugins').mkdir()
        shutil.copyfile(target,packs/'NeverOverworld.zip');shutil.copyfile(nether,packs/'NeverNether.zip');shutil.copyfile(plugin,folder/'plugins/WallsQa.jar')
        (folder/'eula.txt').write_text('eula=true\n')
        (folder/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25618\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\nenable-query=false\nenable-status=false\n')
        for name in ('walls-first','walls-restart'):
            result=r.phase(name,core,folder);report[name]=result;validate(result,build['models'])
        converted=folder/'plugins/R3918ResourceQa/converted'
        s.need(len(list(converted.glob('wall-*.nbt')))==36,'Missing native converted NBT evidence')
        shutil.copytree(converted,OUT/'walls-native-converted')
        s.need(s.sha(core.read_bytes())==fix.fix.CORE and s.sha(base.read_bytes())==fix.fix.BASE and s.sha(nether.read_bytes())==r.NETHER,'Original inputs altered')
        s.need(s.sha((packs/'NeverOverworld.zip').read_bytes())==build['output_sha256'],'Test pack changed')
        report.update({'pass':True,'core_sha256':fix.fix.CORE,'pack_sha256':build['output_sha256'],'scope':'Exact authored Stray Fort recovery, five exact later-author repairs, reviewed dangling template-pool entries removed only when no official model exists, plus two mansion references. Actual wall loading/direct placement; restart reruns scenes, not complete natural assembly of every repaired root.'})
    except Exception as e:report['error']=repr(e)
    finally:
        r.save('walls-result.json',report);print('R3918_WALL_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('build','walls-first','walls-restart')}),flush=True)
    s.need(report['pass'],'Restored wall stage failed')
if __name__=='__main__':main()
