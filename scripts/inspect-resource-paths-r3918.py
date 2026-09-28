#!/usr/bin/env python3
"""Read-only cross-check of actual missing resources against pinned author archives.
Never chooses approximate geometry and never modifies a game archive.
"""
from pathlib import Path
from collections import Counter
import json,sys,urllib.request
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
ext=s.load('r3918_ext',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
sources={};metadata={}
for key in ('dat','towers'):
    spec=ext.SOURCES[key]
    s.need(spec['url'].startswith('https://cdn.modrinth.com/data/'),'Unexpected source URL')
    with urllib.request.urlopen(spec['url'],timeout=60) as response:raw=response.read(60000000)
    s.need(s.sha(raw)==spec['sha256'],'Wrong pinned author bytes '+key)
    sources[key]=ext.flatten_zip(raw);metadata[key]={'sha256':s.sha(raw),'entries':len(sources[key])}
    print('AUTHOR_INPUT',key,json.dumps(metadata[key]),flush=True)
    print('AUTHOR_TEXT_TEMPLATES',key,json.dumps([n for n in sources[key] if '/structure/' in n and not n.endswith('.nbt')]),flush=True)
report=[]
for r in prior['missing']:
    ns,local=r['id'].split(':',1);path='data/'+ns+'/structure/'+local+'.nbt'
    row={'id':r['id'],'origins':r['origins'],'exact_source':[],'same_leaf':[],'other_formats':[]}
    for key,source in sources.items():
        if path in source:row['exact_source'].append({'source':key,'sha256':s.sha(source[path])})
        row['same_leaf'] += [key+':'+n for n in source if Path(n).name==Path(path).name and n!=path]
    row['other_formats']=[n for n in files if n.startswith(path[:-4]+'.') and n!=path]
    report.append(row);print('AUTHOR_GAP',json.dumps(row),flush=True)
for key,source in sources.items():
    print('AUTHOR_WALL_NAMES',key,json.dumps([n for n in source if 'stray_fort_wall' in n and not n.endswith('.json')]),flush=True)
    print('AUTHOR_BOOK_NAMES',key,json.dumps([n for n in source if 'pillager' in n and 'book' in n]),flush=True)
print('PACK_TEXT_TEMPLATES',json.dumps([n for n in files if '/structure/' in n and n.endswith(('.snbt','.json'))]),flush=True)
for n in sorted(pack):
    if n.endswith('.json') and b'minecraft/empty' in pack[n]:print('EMPTY_SENTINEL_REFERENCE',n,pack[n].decode(),flush=True)
print('MINECRAFT_EMPTY_MODEL',json.dumps(ext._nbt_parse(files['data/minecraft/structure/empty.nbt'])[2]),flush=True)
Path('artifacts/author-gap-check.json').write_text(json.dumps({'inputs':metadata,'gaps':report,'game_files_modified':False,'complete_fix':False},indent=2)+'\n')
print('AUTHOR_GAP_INSPECTION_COMPLETE')
