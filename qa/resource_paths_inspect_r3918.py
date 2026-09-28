#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,sys,subprocess
sys.path.insert(0,'qa/field-r3915')
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
report=json.loads(next(Path('candidate-input').rglob('resource-candidates.json')).read_text())
for r in report:
    print('PATH_CANDIDATE',r['missing'],json.dumps([{'path':c['path'],'size':c['size'][1][1],'exact_leaf':c['exact_leaf']} for c in r['candidates']]),flush=True)
print('PALE_DECOR_TEMPLATES',json.dumps([n for n in files if '/pale_residence/decor/' in n and n.endswith('.nbt')]),flush=True)
reader=s.load('r3918_nbt',Path('scripts/build-never-overworld-external-structures-r19.py'))
for n in sorted(files):
    if '/pale_residence/' not in n or not n.endswith('.nbt'):continue
    root=reader._nbt_parse(files[n])[2]
    for b in root.get('blocks',(9,(10,[])))[1][1]:
        nb=b.get('nbt',(10,{}))[1]
        if nb.get('pool')==(8,'nova_structures:pale_residence/decor_inside'):
            print('PALE_INSIDE_CONNECTOR',n,json.dumps({'pos':b.get('pos'),'size':root.get('size'),'nbt':nb}),flush=True)
for n in sorted(files):
    if '/pale_residence/decor/' in n and n.endswith('.nbt'):
        root=reader._nbt_parse(files[n])[2]
        joints=[b.get('nbt',(10,{}))[1] for b in root.get('blocks',(9,(10,[])))[1][1] if 'pool' in b.get('nbt',(10,{}))[1]]
        print('PALE_DECOR',n,json.dumps({'size':root.get('size'),'joints':joints}),flush=True)
libs=Path('.work/r3918-api');libs.mkdir(parents=True,exist_ok=False)
for i,n in enumerate(core):
    if n.endswith('.jar') and n.startswith(('META-INF/libraries/','META-INF/versions/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(core[n])
cp=':'.join(str(p) for p in libs.glob('*.jar'))
for cls in ('net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate','net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings','net.minecraft.world.level.chunk.ProtoChunk','net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplateManager'):
    proc=subprocess.run(['javap','-p','-classpath',cp,cls],capture_output=True,text=True,timeout=30)
    s.need(proc.returncode==0,'javap '+cls);print('RUNTIME_API',proc.stdout,flush=True)
print('COMPACT_INSPECTION_PASS')
