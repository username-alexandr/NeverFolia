#!/usr/bin/env python3
"""Read-only recovery research against official source versions, no approximate remaps."""
from pathlib import Path
import collections,hashlib,importlib.util,io,json,re,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'inventory';OUT.mkdir(exist_ok=False)
HEADERS={'User-Agent':'NeverFolia-resource-recovery/1.0'}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=75) as response:return response.read()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
nbt=load('nbt40',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
def simple(t,v):
    if t==10:return {k:simple(*item) for k,item in v.items()}
    if t==9:return [simple(v[0],x) for x in v[1]]
    if t==7:return list(v)
    return v
def data(raw):return simple(10,nbt._nbt_parse(raw)[2])
def index(z):
    out={}
    for name in z.namelist():
        match=re.fullmatch(r'data/([^/]+)/(?:structure|structures)/(.+)\.nbt',name)
        if match:out[match[1]+':'+match[2]]=name
    return out
missing=json.loads((ROOT/'inspected/resources.json').read_text())['missing']
ids={r['id'] for r in missing};recovery=[]
with zipfile.ZipFile(ROOT/'baseline/world/datapacks/NeverOverworld.zip') as pack:
    known=index(pack);catalog={}
    patterns=('stray_fort/','tavern/tavern_event_trader_car_','lone_citadel/room_content/','bunker/bunker_underground_hallway_','catacomb/hallway/catacomb_path_','desert_ruin/temple/','illager_hideout/illager_hideout_path_short','pale_residence/residence/','village_swamp/','village_jungle/','toxic_lair/')
    for rid,name in known.items():
        if not any(p in rid for p in patterns):continue
        root=data(pack.read(name));palette=root.get('palette',root.get('palettes',[[]])[0]);jigs=[];blocktypes=collections.Counter();important=[]
        for b in root.get('blocks',[]):
            state=palette[b['state']];blocktypes[state['Name']]+=1
            if state['Name']=='minecraft:jigsaw':jigs.append({'pos':b['pos'],'state':state,'nbt':b.get('nbt')})
            elif b.get('nbt') and ('spawner' in state['Name'] or state['Name'] in ('minecraft:chest','minecraft:barrel')):important.append({'pos':b['pos'],'state':state,'nbt':b['nbt']})
        catalog[rid]={'size':root.get('size'),'jigsaws':jigs,'block_types':dict(blocktypes),'entities':root.get('entities',[]),'important_blocks':important,'sha256':hashlib.sha256(pack.read(name)).hexdigest()}
    (OUT/'template-catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    origins={}
    for item in missing:
        for origin in item['origins']:
            if origin.startswith('pool:'):
                ns,path=origin[5:].split(':',1);name='data/'+ns+'/worldgen/template_pool/'+path+'.json'
                if name in pack.namelist():origins[name]=json.loads(pack.read(name))
    (OUT/'missing-origin-pools.json').write_text(json.dumps(origins,indent=2)+'\n')
    for name,obj in origins.items():
        if any(s in name for s in ('stray_fort','pillager','ancient_city','village_','minecraft/empty')):print('R40_POOL',name,json.dumps(obj,separators=(',',':')))
    for rid,row in catalog.items():
        if (('tavern_event_trader_car_' in rid and rid.rsplit('_',1)[-1] in ('cleric','cartographer','armorer','oak','desert')) or ('stray_fort' in rid and any(s in rid for s in ('frame','wall'))) or ('lone_citadel' in rid and any(s in rid for s in ('center','mirror_furnace','mirror_ice')))):
            print('R40_TEMPLATE',rid,json.dumps({k:row[k] for k in ('size','jigsaws')},separators=(',',':')))
    print('R40_BOOK_RELATED',[n for n in pack.namelist() if 'structory_towers' in n and ('book' in n or 'pillager' in n)])
    # Preserve current source hashes before examining older official downloads.
    versions=json.loads(get('https://api.modrinth.com/v2/project/dungeons-and-taverns/version'))
    selected=[]
    for prefix in ('5.2','5.1','5.0','4.'):
        candidates=[v for v in versions if v['version_number'].lstrip('v').startswith(prefix) and 'datapack' in v.get('loaders',[])]
        if candidates:selected.append(candidates[0])
    towers=json.loads(get('https://api.modrinth.com/v2/project/structory-towers/version'))
    tower=[v for v in towers if 'datapack' in v.get('loaders',[])];selected+=tower[:1]
    (OUT/'selected-versions.json').write_text(json.dumps(selected,indent=2)+'\n')
    for v in selected:
        files=[f for f in v['files'] if f.get('primary')];f=files[0] if files else v['files'][0]
        raw=get(f['url']);assert hashlib.sha512(raw).hexdigest()==f['hashes']['sha512'],'Upstream checksum mismatch'
        archive=OUT/(v['id']+'.zip');archive.write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            choices=index(z);found=sorted(ids&set(choices))
            for rid in found:
                payload=z.read(choices[rid]);target=OUT/'exact-recovery'/v['id']/choices[rid];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
                recovery.append({'id':rid,'version_id':v['id'],'version':v['version_number'],'url':f['url'],'archive_sha512':f['hashes']['sha512'],'path':choices[rid],'sha256':hashlib.sha256(payload).hexdigest()})
            print('R40_OLDER_EXACT',v['version_number'],v['id'],json.dumps(found))
            if 'structory' in f['filename'].lower():print('R40_TOWERS_UPSTREAM_BOOKS',[n for n in z.namelist() if 'book' in n or 'pillager' in n])
    (OUT/'exact-recovery.json').write_text(json.dumps(recovery,indent=2)+'\n')
    print('R40_EXACT_RECOVERY_COUNT',len({r['id'] for r in recovery}))
# Relevant source methods are retained whole, rather than inferring from a name.
with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
    needed=('SurfaceSystem.java','SnowAndFreezeFeature.java','ProtoChunk.java','NoiseBasedChunkGenerator.java','NeverOverworldFlood.java')
    for leaf in needed:
        names=[n for n in z.namelist() if n.endswith('/'+leaf) and '/src/minecraft/java/' in n];assert len(names)==1
        text=z.read(names[0]).decode();(OUT/leaf).write_text(text)
        terms={'SurfaceSystem.java':('private void frozenOceanExtension','frozenOceanExtension(','void buildSurface'), 'SnowAndFreezeFeature.java':('public boolean place',), 'ProtoChunk.java':('public ProtoChunk(',), 'NoiseBasedChunkGenerator.java':('int getSeaLevel(',), 'NeverOverworldFlood.java':('collectProtected','protectedBoxes','private static boolean isProtected','getAllStarts') }[leaf]
        lines=text.splitlines();selected_lines=set()
        for i,line in enumerate(lines):
            if any(s in line for s in terms):selected_lines.update(range(max(0,i-3),min(len(lines),i+95)))
        for i in sorted(selected_lines)[:260]:print('R40_EXACT_SOURCE',leaf,i+1,lines[i])
