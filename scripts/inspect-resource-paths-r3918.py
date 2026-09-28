#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys,subprocess,difflib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qa/field-r3915'))
import restore_swift as s
P='0e747781b9ea875631f1453903c0ac912d49f14a3a46ad48bbf604148532c621'
C='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
def exact(folder,name,digest):
    paths=list(Path(folder).rglob(name));s.need(len(paths)==1,'ambiguous '+name)
    raw=paths[0].read_bytes();s.need(s.sha(raw)==digest,'changed '+name);return raw
pack=s.read_zip(exact('integrated-input','NeverOverworld-R3915-Combined.zip',P))
core=s.read_zip(exact('swift-input','server-r3915.jar',C))
inner=[n for n in core if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')];s.need(len(inner)==1,'engine')
engine=s.read_zip(core[inner[0]]);files={**engine,**pack}
ps=list(Path('integrated-input').rglob('combined-resource-after.json'));s.need(len(ps)==1,'audit')
prior=json.loads(ps[0].read_text());s.need(prior['inputs']['pack_sha256']==P,'wrong audit')
allnbt=sorted(n for n in files if n.startswith('data/') and '/structure/' in n and n.endswith('.nbt'))
reader=s.load('r3918_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
report=[]
for r in prior['missing']:
    s.need(r['kind']=='template','unexpected missing family')
    ns,local=r['id'].split(':',1);path='data/'+ns+'/structure/'+local+'.nbt';s.need(path not in files,'stale gap')
    exactleaf=[n for n in allnbt if Path(n).name==Path(path).name]
    close=difflib.get_close_matches(path,[n for n in allnbt if n.startswith('data/'+ns+'/')],n=3,cutoff=.55)
    candidates=[]
    for n in dict.fromkeys(exactleaf+close):
        root=reader._nbt_parse(files[n])[2]
        candidates.append({'path':n,'size':root['size'][1][1],'sha256':s.sha(files[n]),'exact_leaf':n in exactleaf})
    item={'missing':r['id'],'origins':r['origins'],'roots':r['roots'],'candidates':candidates};report.append(item)
    print('PATH_CANDIDATE',r['id'],json.dumps(candidates),flush=True)
Path('artifacts/resource-paths.json').write_text(json.dumps(report,indent=2)+'\n')
for n in sorted(files):
    if '/pale_residence/' not in n or not n.endswith('.nbt'):continue
    root=reader._nbt_parse(files[n])[2]
    joints=[{'pos':b.get('pos'),'nbt':b.get('nbt',(10,{}))[1]} for b in root.get('blocks',(9,(10,[])))[1][1] if 'pool' in b.get('nbt',(10,{}))[1]]
    inside=[b for b in joints if b['nbt'].get('pool')==(8,'nova_structures:pale_residence/decor_inside')]
    if inside:print('PALE_INSIDE_CONNECTOR',n,json.dumps({'size':root.get('size'),'joints':inside}),flush=True)
    if '/decor/' in n:print('PALE_DECOR',n,json.dumps({'size':root.get('size'),'joints':joints}),flush=True)
libs=Path('.work/r3918-api');libs.mkdir(parents=True,exist_ok=False)
for i,n in enumerate(core):
    if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(core[n])
cp=':'.join(str(p) for p in libs.glob('*.jar'))
for cls in ('net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate','net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings','net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplateManager'):
    proc=subprocess.run(['javap','-p','-classpath',cp,cls],capture_output=True,text=True,timeout=30)
    s.need(proc.returncode==0,'javap '+cls);print('RUNTIME_API',proc.stdout,flush=True)
print('COMPACT_INSPECTION_PASS')
