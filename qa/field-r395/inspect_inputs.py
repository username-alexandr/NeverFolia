#!/usr/bin/env python3
"""Read only the exact earlier CI binaries/sources; do not mutate worlds or packs."""
from pathlib import Path
import hashlib, io, json, re, zipfile

out=Path('artifacts'); out.mkdir(exist_ok=True)
with zipfile.ZipFile('debug/diagnostics.zip') as z:
    names=z.namelist()
    wanted=('NeverOverworldFlood.java','NeverOverworldSubmergedRemnants.java','NeverOverworldEcologyR13.java','NeverOverworldEcologyR15.java','NeverOverworldFloodConnectivityR15.java','NeverOverworldWaterAuditR38.java','ChunkLightTask.java')
    for short in wanted:
        found=[n for n in names if n.endswith('/'+short) and '/src/minecraft/java/' in n]
        print('SOURCE_MATCH',short,found)
        if len(found)!=1: continue
        raw=z.read(found[0]); text=raw.decode()
        (out/short).write_bytes(raw)
        print('SOURCE_SHA256',short,hashlib.sha256(raw).hexdigest())
        if short in ('NeverOverworldSubmergedRemnants.java','NeverOverworldEcologyR15.java'):
            print('BEGIN_FULL_SOURCE',short); print(text); print('END_FULL_SOURCE',short)
        else:
            lines=text.splitlines(); keep=set()
            for i,line in enumerate(lines):
                if re.search(r'apply\(|cleanup\(|freeze|ICE|POWDER_SNOW|OCEAN_FLOOR|customOceanColumn|isFloodable|restoreFloodShoreline|waterAudit|NeverOverworld.*\(',line):
                    keep.update(range(max(0,i-5),min(len(lines),i+9)))
            print('BEGIN_SOURCE_EXCERPTS',short)
            for i in sorted(keep):print(f'{i+1}: {lines[i]}')
            print('END_SOURCE_EXCERPTS',short)

packs=list(Path('pack').rglob('NeverOverworld*.zip'))
if len(packs)!=1:raise ValueError(('pack ambiguity',packs))
p=packs[0]; raw=p.read_bytes()
if hashlib.sha256(raw).hexdigest()!='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be':raise ValueError('wrong R39.3 pack')
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    tags={n:json.loads(z.read(n)) for n in z.namelist() if '/tags/enchantment/' in n and n.endswith('.json')}
    ench={n:json.loads(z.read(n)) for n in z.namelist() if re.fullmatch(r'data/[^/]+/enchantment/.+\.json',n)}
    report={'tags':tags,'enchantments':{n:{k:d.get(k) for k in ('description','supported_items','primary_items','max_level','effects')} for n,d in ench.items()}}
    (out/'enchantment-inspection.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print('BEGIN_ENCHANT_TAGS');print(json.dumps(tags,ensure_ascii=False));print('END_ENCHANT_TAGS')
    for n,d in ench.items():
        desc=json.dumps(d.get('description'),ensure_ascii=False)
        print('ENCHANT_DESC',n,desc,'effects=',list(d.get('effects',{})))
        if any(v in desc.lower() for v in ('bug enchant','wither coated','swift soar')):
            print('ENCHANT_DETAIL',n,json.dumps(d,ensure_ascii=False))
print('INSPECTION_DONE')
