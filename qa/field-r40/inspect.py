#!/usr/bin/env python3
"""Read-only input inspection. No modification of kernels, packs or worlds."""
from pathlib import Path
import hashlib,importlib.util,io,json,urllib.request,zipfile
OUT=Path('inventory');OUT.mkdir(exist_ok=True)
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'NeverFolia-resource-compatibility-audit/1.0'})
    with urllib.request.urlopen(req,timeout=90) as r:return r.read()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
jar=Path('baseline/server.jar');pack=Path('baseline/world/datapacks/NeverOverworld.zip')
assert hashlib.sha256(jar.read_bytes()).hexdigest()=='c8886cb5927370e47bfaf8a3ecd274f72880868e0eb2e8fb15bfddde162c7b67'
assert hashlib.sha256(pack.read_bytes()).hexdigest()=='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
with zipfile.ZipFile('debug/diagnostics.zip') as z:
    for leaf in ['CreativeModeTabs.java','ChunkPyramid.java','ChunkLightTask.java']:
        matches=[n for n in z.namelist() if n.endswith('/'+leaf) and '/src/minecraft/java/' in n]
        assert len(matches)==1,(leaf,matches)
        raw=z.read(matches[0]);(OUT/leaf).write_bytes(raw)
        if leaf=='CreativeModeTabs.java':
            lines=raw.decode().splitlines();indexes=set()
            for i,l in enumerate(lines):
                if 'generateEnchantmentBookTypes' in l or 'EnchantmentTags' in l:indexes.update(range(max(0,i-3),min(len(lines),i+35)))
            print('CREATIVE_SOURCE', '\n'.join(f'{i+1}: {lines[i]}' for i in sorted(indexes)),flush=True)
    for n in z.namelist():
        if '/src/minecraft/java/' in n and n.endswith('.java') and 'NeverOverworld' in n:
            raw=z.read(n);lines=raw.decode().splitlines();hits=[i for i,l in enumerate(lines) if 'Blocks.ICE' in l or 'Blocks.PACKED_ICE' in l or 'Blocks.BLUE_ICE' in l or 'FROSTED_ICE' in l]
            if hits:
                (OUT/Path(n).name).write_bytes(raw)
                ix=set(j for i in hits for j in range(max(0,i-5),min(len(lines),i+8)))
                print('ICE_SOURCE',Path(n).name,'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(ix)),flush=True)
with zipfile.ZipFile(pack) as z:
    data={'enchantments':{n:json.loads(z.read(n)) for n in z.namelist() if n.startswith('data/nova_structures/enchantment/') and n.endswith('.json')},'lang':[n for n in z.namelist() if '/lang/' in n],'pack':json.loads(z.read('pack.mcmeta'))}
    (OUT/'enchantments.json').write_text(json.dumps(data,indent=2,ensure_ascii=False))
    print('PACK_META',json.dumps(data['pack']));print('LANG_ASSETS',json.dumps(data['lang']))
    for n,v in data['enchantments'].items():print('ENCHANT',n,json.dumps({k:v[k] for k in ('description','max_level','supported_items','slots') if k in v}))
    names=set(z.namelist())
    # An original author build for the exact same MC version: never install it wholesale.
    v=json.loads(get('https://api.modrinth.com/v2/version/CS77UwHE'))
    assert v['project_id']=='tpehi7ww' and '26.2' in v['game_versions'] and 'datapack' in v['loaders']
    file=next(f for f in v['files'] if f['primary']);assert file['url'].startswith('https://cdn.modrinth.com/')
    original=get(file['url']);assert hashlib.sha512(original).hexdigest()==file['hashes']['sha512']
    (OUT/'upstream-version.json').write_text(json.dumps(v,indent=2));(OUT/'Dungeons-and-Taverns-5.3.2.zip').write_bytes(original)
    a=load('audit40','scripts/audit-neveroverworld-r39-resources.py');report=a.audit_files(jar,pack)
    (OUT/'resource-gaps.json').write_text(json.dumps(report,indent=2))
    print('COUNTS',json.dumps(report['counts']),flush=True)
    with zipfile.ZipFile(io.BytesIO(original)) as upstream:
        known=set(upstream.namelist());resolved=[]
        for row in report['missing']:
            ns,path=row['id'].split(':',1);exact=f'data/{ns}/structure/{path}.nbt'
            candidates=sorted(n for n in known|names if n.endswith('/'+path.rsplit('/',1)[-1]+'.nbt'))
            print('GAP',row['id'],'exact_upstream=',exact in known,'same_leaf=',candidates[:10],flush=True)
            if exact in known:resolved.append(exact)
        print('UPSTREAM_EXACT_RECOVERABLE',len(resolved),flush=True)
