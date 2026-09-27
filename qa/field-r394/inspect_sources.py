#!/usr/bin/env python3
"""Read-only resource provenance investigation. No donor is enabled automatically."""
from pathlib import Path
import argparse,collections,hashlib,importlib.util,io,json,re,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def get(url,limit=100*1024*1024):
    if not url.startswith(('https://api.modrinth.com/','https://cdn.modrinth.com/')):raise ValueError('Nonofficial donor endpoint')
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'NeverFolia/resource-diagnostics'}),timeout=60) as r:data=r.read(limit+1)
    if len(data)>limit:raise ValueError('Download size limit')
    return data

def plain(tag):
    kind,v=tag
    if kind==10:return {k:plain(t) for k,t in v.items()}
    if kind==9:return [plain((v[0],x)) for x in v[1]]
    if isinstance(v,bytes):return {'bytes':len(v)}
    return v

def summary(builder,raw):
    _,_,typed=builder._nbt_parse(raw);obj=plain((10,typed))
    palettes=[obj['palette']] if 'palette' in obj else obj.get('palettes',[])
    joints=[];spawners=[]
    for b in obj.get('blocks',[]):
        n=b.get('nbt',{});states=[p[b['state']] for p in palettes]
        if 'pool' in n or any(s.get('Name')=='minecraft:jigsaw' for s in states):joints.append({'pos':b['pos'],'states':states,'nbt':n})
        if n.get('id') in ('minecraft:mob_spawner','minecraft:spawner','minecraft:trial_spawner'):spawners.append({'pos':b['pos'],'nbt':n})
    return {'sha256':sha(raw),'size':obj.get('size'),'jigsaws':joints,'spawners':spawners,'entity_count':len(obj.get('entities',[])),'block_count':len(obj.get('blocks',[]))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--debug',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    builder=module('r394_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    closure=json.loads((a.evidence/'r393-resource-closure.json').read_text());missing=[r for r in closure['missing'] if r['kind']=='template']
    packraw=(a.candidate/'NeverOverworld.zip').read_bytes()
    if sha(packraw)!='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be':raise ValueError('Unexpected R39.3 bytes')
    with zipfile.ZipFile(io.BytesIO(packraw)) as z:
        names=set(z.namelist());selected={}
        for row in missing:
            ns,path=row['id'].split(':',1);base=path.rsplit('/',1)[-1];family=path.split('/',1)[0]
            candidates=[n for n in names if n.startswith('data/'+ns+'/structure/') and n.endswith('/'+base+'.nbt')]
            selected[row['id']]={'origins':row['origins'],'exact_basename':candidates}
        profiles={}
        for name in sorted(names):
            if '/structure/' not in name or not name.endswith('.nbt'):continue
            if any(v in name for v in ('stray_fort_wall','stray_fort_path_t','trader_car','lone_citadel/room_content/deko_','illager_hideout_path_short_s','jungle_village_path5','swamp_village_big_house','swamp_village_path5')):
                profiles[name]=summary(builder,z.read(name))
        save(a.output/'existing-profiles.json',profiles);save(a.output/'same-basename.json',selected)
        print('EXACT_BASENAME',json.dumps({k:v for k,v in selected.items() if v['exact_basename']}),flush=True)
        print('STRAY_NAMES',json.dumps([n for n in sorted(names) if '/structure/stray_fort/' in n and any(t in n for t in ('wall','path_t'))]),flush=True)
        print('TRADER_NAMES',json.dumps([n for n in sorted(names) if '/structure/tavern/' in n and 'trader_car' in n]),flush=True)
    # Preserve only source texts useful for the next actual placement test, not the huge diagnostic bundle.
    with zipfile.ZipFile(a.debug/'diagnostics.zip') as z:
        wanted=('StructureTemplate.java','StructurePlaceSettings.java','StructureTemplateManager.java','Commands.java','GameProtocols.java','ChunkStatus.java','ServerLevel.java','PlaceCommand.java')
        index=[n for n in z.namelist() if n.endswith(wanted)]
        save(a.output/'debug-index.json',index)
        for n in index:
            out=a.output/'engine-source'/n;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(n))
        print('DEBUG_JARS',json.dumps([n for n in z.namelist() if n.endswith('.jar')]),flush=True)
        print('ENGINE_SOURCES',json.dumps(index),flush=True)
    # Query creator-hosted releases, then compare complete source archives before importing anything.
    versions=json.loads(get('https://api.modrinth.com/v2/project/tpehi7ww/version',4*1024*1024))
    versions=[v for v in versions if 'datapack' in v['loaders'] and ('26.2' in v['game_versions'] or v['version_number'].startswith('5.3'))]
    versions.sort(key=lambda v:v['date_published'],reverse=True)
    chosen=versions[:4]
    save(a.output/'available-versions.json',[{k:v[k] for k in ('id','version_number','date_published','game_versions')} for v in versions])
    matches={row['id']:[] for row in missing};inputs=[]
    for v in chosen:
        file=next((f for f in v['files'] if f.get('primary')),v['files'][0]);raw=get(file['url'])
        if hashlib.sha512(raw).hexdigest()!=file['hashes']['sha512']:raise ValueError('Source hash mismatch')
        effective=builder.flatten_zip(raw);ident={'version':v['version_number'],'version_id':v['id'],'url':file['url'],'sha256':sha(raw),'game_versions':v['game_versions']}
        inputs.append(ident)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            archive_names=archive.namelist()
            for row in missing:
                ns,path=row['id'].split(':',1);wanted='data/'+ns+'/structure/'+path+'.nbt'
                if wanted in effective:
                    data=effective[wanted];target=a.output/'donors'/v['id']/wanted;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    matches[row['id']].append({'version_id':v['id'],'version':v['version_number'],'path':wanted,**summary(builder,data)})
                elif any(n.endswith('/'+path.rsplit('/',1)[-1]+'.nbt') for n in archive_names):
                    selected[row['id']].setdefault('source_other_paths',{})[v['id']]=[n for n in archive_names if n.endswith('/'+path.rsplit('/',1)[-1]+'.nbt')]
        print('DONOR_SOURCE',json.dumps(ident),'exact_matches',sum(any(x['version_id']==v['id'] for x in entries) for entries in matches.values()),flush=True)
    save(a.output/'donor-matches.json',matches);save(a.output/'source-provenance.json',inputs);save(a.output/'same-basename.json',selected)
    print('DONOR_MATCHES',json.dumps({k:[{'version':x['version'],'size':x['size']} for x in v] for k,v in matches.items() if v}),flush=True)
    print('DONOR_UNRESOLVED',json.dumps([k for k,v in matches.items() if not v]),flush=True)
    save(a.output/'scope.json',{'read_only':True,'pack_sha256':sha(packraw),'donors_enabled':False,'missing_count':len(missing),'matching_donor_count':sum(bool(v) for v in matches.values()),'runtime_tested':False})
if __name__=='__main__':main()
