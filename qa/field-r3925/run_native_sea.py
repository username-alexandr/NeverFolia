#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,zipfile

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'.work/r3925-native-sea'
OUT=ROOT/'artifacts-r3925-native-sea'

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def exact(root,name,digest):
    hits=[p for p in Path(root).rglob(name) if p.is_file() and sha(p)==digest]
    need(len(hits)==1,f'exact input {name} {digest}: {hits}')
    return hits[0]

def compile_plugin(core):
    libs=WORK/'libs';classes=WORK/'classes';libs.mkdir(parents=True);classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,name in enumerate(z.namelist()):
            if name.endswith('.jar') and name.startswith(('META-INF/versions/','META-INF/libraries/')):
                (libs/f'{i}-{Path(name).name}').write_bytes(z.read(name))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')));need(cp,'empty server classpath')
    src=ROOT/'qa/field-r3925/R3925NativeSeaQa.java'
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(src)],text=True,capture_output=True)
    (OUT/'javac.log').write_text(p.stdout+p.stderr);need(p.returncode==0,'R3925 QA plugin compile failed')
    plugin=WORK/'R3925NativeSeaQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3925NativeSeaQa\nversion: '3925'\nmain: R3925NativeSeaQa\napi-version: '26.2'\nfolia-supported: true\n")
    return plugin

def edge_stats(rows):
    by={(r['chunk_x'],r['chunk_z']):r for r in rows}
    seams=[]
    for (cx,cz),r in sorted(by.items()):
        east=by.get((cx+1,cz))
        if east:
            dif=[abs(a-b) for a,b in zip(r['east_solid_edge'],east['west_solid_edge'])]
            seams.append({'axis':'x','a':[cx,cz],'b':[cx+1,cz],'max_delta':max(dif),'big24':sum(d>=24 for d in dif),'deltas':dif})
        south=by.get((cx,cz+1))
        if south:
            dif=[abs(a-b) for a,b in zip(r['south_solid_edge'],south['north_solid_edge'])]
            seams.append({'axis':'z','a':[cx,cz],'b':[cx,cz+1],'max_delta':max(dif),'big24':sum(d>=24 for d in dif),'deltas':dif})
    flags=[s for s in seams if s['big24']>=8]
    return seams,flags

def pack_audit(pack):
    with zipfile.ZipFile(pack) as z:
        need(z.testzip() is None,'pack CRC failure')
        noise=json.loads(z.read('data/minecraft/worldgen/noise_settings/overworld.json'))
        need(noise.get('sea_level')==128,'pack sea_level is not 128')
        def ids(name):
            d=json.loads(z.read(name));return {v if isinstance(v,str) else v['id'] for v in d.get('values',[])}
        game=ids('data/nova_structures/tags/enchantment/all_dnt_enchants.json')
        tech=ids('data/nova_structures/tags/enchantment/non_survival_enchants.json')
        need(len(game)==17 and len(tech)==16 and not game&tech,'enchantment partition invalid')
        need('nova_structures:jockey/spawn_ravager_jockey' in tech,'ravager technical enchant unclassified')
        for rid in tech:
            ns,name=rid.split(':',1);d=json.loads(z.read(f'data/{ns}/enchantment/{name}.json'))
            need(d.get('max_level')==1,'technical max_level != 1: '+rid)
            need(d.get('description')=={'text':''},'technical description visible: '+rid)
        return {'sea_level':128,'gameplay_count':17,'technical_count':16,'ravager_classified':True}

def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    core_sha=os.environ['R3925_CORE_SHA'];ow_sha=os.environ['R3925_OW_SHA'];nn_sha=os.environ['R3925_NN_SHA']
    core=exact(ROOT/'core-input',os.environ['R3925_CORE_NAME'],core_sha)
    ow=exact(ROOT/'ow-input','NeverOverworld-R3925-NativeSea.zip',ow_sha)
    nn=exact(ROOT/'nn-input','NeverNether.zip',nn_sha)
    static=pack_audit(ow);plugin=compile_plugin(core)

    srv=WORK/'server';packs=srv/'world/datapacks';plugins=srv/'plugins';packs.mkdir(parents=True);plugins.mkdir()
    shutil.copyfile(ow,packs/'NeverOverworld.zip');shutil.copyfile(nn,packs/'NeverNether.zip');shutil.copyfile(plugin,plugins/'R3925NativeSeaQa.jar')
    (srv/'eula.txt').write_text('eula=true\n')
    (srv/'server.properties').write_text(
      'level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
      'server-ip=127.0.0.1\nserver-port=25625\nonline-mode=false\nenforce-secure-profile=false\n'
      'enable-rcon=false\nenable-query=false\nenable-status=false\nview-distance=2\nsimulation-distance=2\n'
      'spawn-protection=0\npause-when-empty-seconds=-1\nmax-tick-time=-1\n'
    )
    r399=OUT/'r399';ice=OUT/'r3913';r399.mkdir();ice.mkdir()
    log=OUT/'server.log'
    cmd=['java','-XX:ActiveProcessorCount=4','-Xms1G','-Xmx5G',
         '-Dneverfolia.r399OceanClosure=true','-Dneverfolia.r3913IceFragments=true',
         '-Dneverfolia.r399ReportDirectory='+str(r399.resolve()),
         '-Dneverfolia.r3913IceReport='+str(ice.resolve()),
         '-jar',str(core.resolve()),'--nogui']
    with log.open('w') as out:
        proc=subprocess.Popen(cmd,cwd=srv,stdin=subprocess.PIPE,stdout=out,stderr=subprocess.STDOUT,text=True)
        try:code=proc.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            try:proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=60)
            except Exception:proc.kill();code=proc.wait()
            raise ValueError('native-sea server timeout')
    result_path=plugins/'R3925NativeSeaQa/result.json'
    need(code==0,'server exit '+str(code));need(result_path.is_file(),'QA result missing')
    result=json.loads(result_path.read_text());need(result.get('pass') is True,'plugin failure: '+repr(result.get('error')))
    need(result['completed_chunks']==result['target_chunks'],'incomplete chunk sampling')

    rows=result['chunks']
    totals={
      'chunks':len(rows),
      'wet_columns':sum(r['wet_columns'] for r in rows),
      'air_gap_cells_in_wet_columns':sum(r['air_gap_cells_in_wet_columns'] for r in rows),
      'surface_gap_columns':sum(r['surface_gap_columns'] for r in rows),
      'living_floor_columns':sum(r['living_floor_columns'] for r in rows),
      'flowing_water_cells_in_wet_columns':sum(r['flowing_water_cells_in_wet_columns'] for r in rows),
      'water_cells_y128_or_above':sum(r['water_cells_y128_or_above'] for r in rows),
    }
    seams,seam_flags=edge_stats(rows)
    server_text=log.read_text(errors='replace')
    need('Native fluid picker active' in server_text and 'seaLevel=128' in server_text,'native fluid picker seaLevel=128 not observed')
    need(totals['air_gap_cells_in_wet_columns']==0,'AIR gaps remain in wet ocean columns')
    need(totals['surface_gap_columns']==0,'dry caps remain above ocean water')
    need(totals['living_floor_columns']==0,'living grass/podzol/moss floor remains underwater')
    need(totals['flowing_water_cells_in_wet_columns']==0,'flowing-water curtains remain inside ocean columns')
    need(not list(r399.glob('*.json')),'R399 wrote evidence in native sea mode')
    need(not list(ice.glob('*.json')),'R3913 wrote evidence in native sea mode')

    summary={
      'pass':True,'inputs':{'core_sha256':core_sha,'overworld_sha256':ow_sha,'nether_sha256':nn_sha},
      'static_pack':static,'totals':totals,'seam_flags_big24_ge8':seam_flags,
      'seam_count':len(seams),'seam_flag_count':len(seam_flags),
      'synthetic_r399_reports':0,'synthetic_r3913_reports':0,
      'production_accepted':False
    }
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'seams.json').write_text(json.dumps({'seams':seams,'flags':seam_flags},indent=2)+'\n')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R3925_NATIVE_SEA '+json.dumps(summary),flush=True)

if __name__=='__main__':main()
