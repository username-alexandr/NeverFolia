#!/usr/bin/env python3
"""Read pinned CI artifacts only; never alter game binaries or worlds."""
from pathlib import Path
import hashlib, json, re, zipfile
out=Path('artifacts');out.mkdir(exist_ok=True)
manifest={}
for p in sorted(Path('evidence').rglob('*')):
    if not p.is_file():continue
    manifest[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    if p.suffix=='.json':
        try:doc=json.loads(p.read_text())
        except (UnicodeError,ValueError):continue
        print('EVIDENCE_JSON',p,'KEYS',list(doc)[:45] if isinstance(doc,dict) else 'list')
        if isinstance(doc,dict):
            def trim(v,depth=0):
                if depth>5:return '<nested>'
                if isinstance(v,dict):return {k:trim(x,depth+1) for k,x in v.items() if k not in ('chunks','sections','block_counts','enchantment_visibility','rows','block_states')}
                if isinstance(v,list):return [trim(x,depth+1) for x in v[:12]]+([{'additional_items':len(v)-12}] if len(v)>12 else [])
                return v
            print(json.dumps(trim(doc),ensure_ascii=False))
with zipfile.ZipFile('debug/diagnostics.zip') as z:
    wanted={'NeverOverworldChunkWeathering.java','NeverOverworldCaveSeamCleaner.java','NeverOverworldSubmergedRemnants.java','ChunkLightTask.java','NeverOverworldEcologyR13.java','NeverOverworldEcologyR15.java'}
    found={}
    for name in z.namelist():
        if '/src/minecraft/java/' not in name or Path(name).name not in wanted:continue
        raw=z.read(name);base=Path(name).name
        if base in found:raise ValueError('Duplicate materialized source: '+base)
        found[base]=name;(out/base).write_bytes(raw)
        manifest[name]=hashlib.sha256(raw).hexdigest()
        lines=raw.decode().splitlines()
        if base in ('NeverOverworldCaveSeamCleaner.java','NeverOverworldSubmergedRemnants.java','ChunkLightTask.java'):
            selected=set(range(len(lines)))
        else:
            selected=set()
            for n,line in enumerate(lines):
                if re.search(r'public static|setBlockState|Blocks\.(WATER|AIR|GRASS_BLOCK|ICE)|OCEAN_FLOOR|waterContact|afterPlantRemoval|SNOW',line):selected.update(range(max(0,n-10),min(len(lines),n+14)))
        print('\nSOURCE_BEGIN',base,'sha256='+hashlib.sha256(raw).hexdigest(),'lines='+str(len(lines)))
        last=-2
        for i in sorted(selected):
            if i!=last+1:print('...')
            print(str(i+1)+': '+lines[i]);last=i
        print('SOURCE_END',base)
    if not {'NeverOverworldCaveSeamCleaner.java','ChunkLightTask.java'}<=set(found):raise ValueError('Missing required materialized source')
(out/'inspection-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('READ_ONLY_INSPECTION_DONE')
