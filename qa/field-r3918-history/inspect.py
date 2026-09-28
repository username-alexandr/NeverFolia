#!/usr/bin/env python3
"""Read-only model recovery inventory from official project versions.
Does not install old packs or modify the integrated candidate. Matches exact
resource IDs only, including the documented legacy structures/ directory.
"""
from pathlib import Path,PurePosixPath
from urllib.parse import urlparse
import hashlib,io,json,re,sys,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'qa/field-r3915'))
import restore_swift as s
OUT=ROOT/'history-artifacts';OUT.mkdir(exist_ok=True)
PACK='0e747781b9ea875631f1453903c0ac912d49f14a3a46ad48bbf604148532c621'

def get(url,limit,host):
    s.need(urlparse(url).scheme=='https' and urlparse(url).hostname==host,'Unexpected download host')
    req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-resource-recovery/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:
        s.need(urlparse(r.url).hostname==host,'Unexpected redirect')
        raw=r.read(limit+1)
    s.need(len(raw)<=limit,'Response exceeds bound');return raw

def resource(entry):
    p=PurePosixPath(entry)
    s.need(not p.is_absolute() and '..' not in p.parts and '\\' not in entry,'Unsafe archive member')
    parts=p.parts
    positions=[i for i,x in enumerate(parts) if x=='data']
    if len(positions)!=1:return None
    i=positions[0];tail=parts[i:]
    if len(tail)<4 or tail[2] not in ('structure','structures') or not tail[-1].endswith('.nbt'):return None
    ident=tail[1]+':'+('/'.join(tail[3:]))[:-4]
    if re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+',ident) is None:return None
    return ident

def main():
    paths=list((ROOT/'integrated-input').rglob('combined-resource-after.json'));s.need(len(paths)==1,'Previous audit absent')
    prior=json.loads(paths[0].read_text());s.need(prior['inputs']['pack_sha256']==PACK,'Wrong prior audit')
    missing={r['id'] for r in prior['missing'] if r['kind']=='template'}
    closure={
        *('nova_structures:stray_fort/stray_fort_event_'+str(i) for i in range(1,16)),
        *('nova_structures:stray_fort/stray_fort_event_'+str(i)+'b' for i in range(1,16)),
        *('nova_structures:stray_fort/stray_fort_path_'+str(i) for i in range(1,5)),
    }
    targets=missing|closure
    ext=s.load('r3918_history_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    report={'inspection_only':True,'game_files_modified':False,'all_reported_bugs_fixed':False,'base_pack_sha256':PACK,'versions':[],'metadata':[],'current_source_references':{}}
    selections=[]
    for project,prefixes in [('tpehi7ww',('4.5','4.6','5.0','5.1','5.2','5.3','6.')),('j3FONRYr',('1.0.13','1.0.14','1.0.15','1.0.16','1.0.17'))]:
        raw=get('https://api.modrinth.com/v2/project/'+project+'/version',5000000,'api.modrinth.com')
        versions=json.loads(raw);s.need(isinstance(versions,list),'Invalid version metadata')
        report['metadata'].append({'project':project,'sha256':s.sha(raw),'records':len(versions)})
        for prefix in prefixes:
            eligible=[v for v in versions if v.get('project_id')==project and 'datapack' in v.get('loaders',[]) and v.get('version_type')=='release' and v.get('version_number','').lower().lstrip('v').startswith(prefix)]
            if not eligible:
                report['versions'].append({'project':project,'requested_prefix':prefix,'status':'no_matching_official_release'});continue
            v=max(eligible,key=lambda x:x['date_published']);selections.append((project,prefix,v))
    s.need(len(selections)<=12,'Inspection scope exceeded')
    for project,prefix,v in selections:
        row={'project':project,'version_id':v['id'],'version_number':v['version_number'],'requested_prefix':prefix,'status':'not_finished','matches':[],'event13b_references':[]};report['versions'].append(row)
        try:
            files=[x for x in v['files'] if x.get('primary') is True and x['filename'].endswith('.zip')]
            s.need(len(files)==1,'Missing unique primary datapack')
            f=files[0];s.need(f['url'].startswith('https://cdn.modrinth.com/data/'+project+'/versions/'+v['id']+'/'),'File does not belong to selected official version')
            s.need(0<f['size']<=60000000,'Unreviewed archive size')
            raw=get(f['url'],60000000,'cdn.modrinth.com')
            s.need(len(raw)==f['size'] and hashlib.sha512(raw).hexdigest()==f['hashes']['sha512'],'Official file size/hash mismatch')
            row.update({'url':f['url'],'sha256':s.sha(raw),'sha512':f['hashes']['sha512'],'size':len(raw)})
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                s.need(len(z.infolist())<=30000 and sum(n.file_size for n in z.infolist())<=500000000,'Unreviewed decompressed scope')
                s.need(len(z.namelist())==len(set(z.namelist())),'Duplicate zip entries')
                current=(project=='tpehi7ww' and prefix=='5.3') or (project=='j3FONRYr' and prefix=='1.0.17')
                if current:
                    refs={}
                    needles={ident:ident.encode() for ident in missing}
                    for info in z.infolist():
                        if not info.filename.endswith(('.json','.mcfunction')) or info.file_size>2000000:continue
                        payload=z.read(info)
                        for ident,needle in needles.items():
                            if needle in payload:refs.setdefault(ident,[]).append(info.filename)
                    report['current_source_references'][project]={k:sorted(v) for k,v in sorted(refs.items())}
                for n in z.infolist():
                    if (n.filename.endswith('.json') or n.filename.endswith('.mcfunction')) and n.file_size<=2000000:
                        payload=z.read(n)
                        if b'stray_fort_event_13b' in payload:
                            row['event13b_references'].append({'entry':n.filename,'sha256':s.sha(payload),'excerpt':payload.decode('utf-8',errors='replace')[:12000]})
                    ident=resource(n.filename)
                    if ident not in targets:continue
                    s.need(n.file_size<=5000000,'Oversized model')
                    payload=z.read(n);root=ext._nbt_parse(payload)[2]
                    row['matches'].append({'id':ident,'entry':n.filename,'sha256':s.sha(payload),'size':root.get('size'),'data_version':root.get('DataVersion')})
            row['status']='checked'
        except Exception as e:row['status']='failed';row['error']=repr(e)
        print('HISTORICAL_RESOURCE_CHECK',json.dumps(row),flush=True)
        (OUT/'history-check.json').write_text(json.dumps(report,indent=2)+'\n')
    allfound=sorted({m['id'] for r in report['versions'] if r['status']=='checked' for m in r['matches']})
    report['exact_candidate_ids']=allfound
    report['unresolved_in_checked_versions']=sorted(missing-set(allfound))
    report['closure_target_ids']=sorted(closure)
    report['closure_unresolved_in_checked_versions']=sorted(closure-set(allfound))
    report['complete_inspection']=all(r['status']!='failed' for r in report['versions'])
    (OUT/'history-check.json').write_text(json.dumps(report,indent=2)+'\n')
    # Trace the one unresolved vanilla-namespaced template through every
    # pinned source archive used by the NeverOverworld builder. This decides
    # which source owns the dangling reference before any repair is attempted.
    ancient='minecraft:ancient_city/walls/intact_horizontal_wall_stairs_5'
    builder=s.load('r3918_history_sources',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    source_trace=[]
    for key,meta in builder.SOURCES.items():
        raw=get(meta['url'],60000000,'cdn.modrinth.com')
        s.need(s.sha(raw)==meta['sha256'],'Pinned source changed: '+key)
        refs=[];templates=[]
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for info in z.infolist():
                ident=resource(info.filename)
                if ident==ancient:templates.append(info.filename)
                if info.filename.endswith(('.json','.mcfunction')) and info.file_size<=2000000:
                    payload=z.read(info)
                    if ancient.encode() in payload:refs.append(info.filename)
        source_trace.append({'source':key,'references':sorted(refs),'templates':sorted(templates)})
    report['ancient_city_trace']=source_trace
    core_paths=list((ROOT/'core-input').rglob('server-r3915.jar'))
    s.need(len(core_paths)==1,'Pinned core input missing for vanilla trace')
    core=core_paths[0]
    s.need(s.sha(core.read_bytes())=='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40','Pinned core changed')
    vanilla_trace={'outer_sha256':s.sha(core.read_bytes()),'references':[],'templates':[]}
    with zipfile.ZipFile(core) as outer:
        nested=[n for n in outer.namelist() if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
        s.need(len(nested)==1,'Pinned nested Folia jar missing')
        nested_raw=outer.read(nested[0]);vanilla_trace['nested_sha256']=s.sha(nested_raw)
    with zipfile.ZipFile(io.BytesIO(nested_raw)) as vanilla:
        target='data/minecraft/structure/ancient_city/walls/intact_horizontal_wall_stairs_5.nbt'
        if target in vanilla.namelist():vanilla_trace['templates'].append(target)
        needle=ancient.encode()
        for info in vanilla.infolist():
            if info.filename.endswith('.json') and info.file_size<=2000000:
                payload=vanilla.read(info)
                if needle in payload:
                    vanilla_trace['references'].append(info.filename)
                    vanilla_trace.setdefault('reference_payloads',{})[info.filename]=json.loads(payload)
    report['ancient_city_vanilla_trace']=vanilla_trace
    (OUT/'history-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print('ANCIENT_CITY_VANILLA_TRACE',json.dumps(vanilla_trace,sort_keys=True),flush=True)
    print('HISTORICAL_EXACT_CANDIDATES',json.dumps(allfound),flush=True)
    print('UNRESOLVED_ORIGINAL',json.dumps(sorted(missing-set(allfound))),flush=True)
    print('CURRENT_SOURCE_REFERENCES',json.dumps(report['current_source_references'],sort_keys=True),flush=True)
    print('ANCIENT_CITY_TRACE',json.dumps(source_trace,sort_keys=True),flush=True)
    s.need(report['complete_inspection'],'Some author archive inspections failed; absence is not proven')
if __name__=='__main__':main()
