#!/usr/bin/env python3
"""Reproducible diagnostic combination, not a production build or full Gradle."""
from pathlib import Path
import ast, difflib, hashlib, json, sys, zipfile
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts'
OUT.mkdir(exist_ok=True)
source = ROOT / 'qa/field-r395/build_candidate.py'
text = source.read_text()

def once(value, old, new):
    if value.count(old) != 1:
        raise ValueError('Source drift: ' + old[:100])
    return value.replace(old, new, 1)

adapter = ROOT / 'native/overworld-r395/NeverOverworldOceanClosureR395.java'
raw = adapter.read_bytes()
blob = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
if blob != 'd022c60f5c08a156f00154ddf85ab5882f3aaa39':
    raise ValueError('Unexpected R395 adapter source: ' + blob)
old = raw.decode()
anchor = '        OceanConnectivityR395.Proof proof=OceanConnectivityR395.solve(WIDTH,WIDTH,HEIGHT,cells,sky,extraLava);'
new = once(old, anchor, anchor + '\n        OceanWitnessR397.record(REPORT,cx,cz,cells,sky,extraLava,proof);')
generated = OUT / 'generated-source'
generated.mkdir(exist_ok=False)
updated = generated / adapter.name
updated.write_text(new)
(OUT/'adapter.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=str(adapter.relative_to(ROOT)),tofile='generated-source/'+adapter.name)))
policy = ROOT/'native/overworld-r38/NeverOverworldWaterPolicyR38.java'
if hashlib.sha256(policy.read_bytes()).hexdigest() != 'f2f75f2ed71228da3d0637c77c7b892466b4b1b195571196a2de35fca2267fdb':
    raise ValueError('R396 independently tested policy does not match')
old_line = "java_sources=[str(p) for p in sorted((ROOT/'native/overworld-r395').glob('*.java'))]+[str(light)]"
new_line = "java_sources=[str(p) for p in sorted((ROOT/'native/overworld-r395').glob('*.java')) if p.name!='NeverOverworldOceanClosureR395.java']+[str(OUT/'generated-source/NeverOverworldOceanClosureR395.java'),str(ROOT/'native/overworld-r38/NeverOverworldWaterPolicyR38.java'),str(light)]"
text = once(text,old_line,new_line)
ast.parse(text)
(OUT/'generated-build.py').write_text(text)
sys.path.insert(0,str(source.parent))
exec(compile(text,str(source),'exec'),{'__name__':'__main__','__file__':str(source)})
report=json.loads((OUT/'build.json').read_text())
key='net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class'
if key not in report['changed_or_added_classes']:
    raise ValueError('R396 policy not actually compiled into candidate')
report.update({'experiment':'R397 seam witness with R396 removal policy','r396_policy_included':True,'diagnostic_witness_only':True,'production_accepted':False})
(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n')
# Export the real materialized cleanup implementations for review, not guesses.
with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
    wanted={'NeverOverworldSubmergedRemnants.java','NeverOverworldEcologyR13.java','NeverOverworldEcologyR15.java','ChunkLightTask.java'}
    for name in z.namelist():
        if '/src/minecraft/java/' in name and Path(name).name in wanted:
            payload=z.read(name)
            (generated/('R38-'+Path(name).name)).write_bytes(payload)
            print('\nMATERIALIZED_SOURCE',name,'\n'+payload.decode(),flush=True)
print('R397_COMBINED_BUILD',json.dumps(report),flush=True)
