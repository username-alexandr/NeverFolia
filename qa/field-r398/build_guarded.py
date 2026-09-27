#!/usr/bin/env python3
"""Incremental exact-R38 candidate: R396 policy + R395 opt-in closure + FULL guards.
No production world is opened. Existing acceptance gates are not modified.
"""
from pathlib import Path
import ast,difflib,hashlib,json,re,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts';OUT.mkdir(exist_ok=True)
GENERATED=OUT/'r398-generated';GENERATED.mkdir(exist_ok=False)
SOURCES={
 'NeverOverworldFlood.java':('e9a68ef34c78988f1d584cbf14889f312872cc9f04b53aa9b44c744157d6bc27',[('reweatherSubmergedSurface','chunk','void')]),
 'NeverOverworldFloodConnectivityR15.java':('064f5f7b1a418b57b0706b3789fc362353b60f2fb41957ebe3f763e94c16110e',[('apply','chunk','int'),('reconcileSeams','owner','int')]),
 'NeverOverworldSubmergedRemnants.java':('f038b3ed3842e1c8133830d21a299ee1a8d1f9ba4e953eb712d784b569361078',[('apply','chunk','void')]),
}
def need(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def once(text,old,new):
 need(text.count(old)==1,'Source drift at '+old[:100]);return text.replace(old,new,1)
changes=[]
with zipfile.ZipFile(ROOT/'debug/diagnostics.zip') as z:
 for base,(expected,methods) in SOURCES.items():
  matches=[n for n in z.namelist() if n.endswith('/src/minecraft/java/net/minecraft/world/level/chunk/'+base)]
  need(len(matches)==1,'Ambiguous/missing exact source '+base)
  original=z.read(matches[0]);need(sha(original)==expected,'Materialized source changed: '+base)
  text=original.decode()
  for method,argument,result in methods:
   pattern=r'public static '+result+r' '+method+r'\([^)]*\)\s*\{'
   matches_method=list(re.finditer(pattern,text));need(len(matches_method)==1,'Ambiguous method '+method)
   end=matches_method[0].end()
   guard='\n        // R398: generation cleanup must never mutate a persisted FULL chunk.\n        if ('+argument+' != null && '+argument+'.getPersistedStatus().isOrAfter(net.minecraft.world.level.chunk.status.ChunkStatus.FULL)) return'+(' 0' if result=='int' else '')+';\n'
   text=text[:end]+guard+text[end:]
  (GENERATED/base).write_text(text)
  (GENERATED/(base+'.patch')).write_text(''.join(difflib.unified_diff(original.decode().splitlines(True),text.splitlines(True),fromfile='a/'+base,tofile='b/'+base)))
  changes.append({'file':base,'source_sha256':expected,'patched_sha256':sha(text.encode()),'methods':[m[0] for m in methods]})
policy=ROOT/'native/overworld-r38/NeverOverworldWaterPolicyR38.java'
need(sha(policy.read_bytes())=='f2f75f2ed71228da3d0637c77c7b892466b4b1b195571196a2de35fca2267fdb','Exact tested R396 policy missing')
source=ROOT/'qa/field-r395/build_candidate.py'
raw=source.read_bytes();need(hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()=='fabb5ee6a2803a1d12797b2bf927773d1340e195','R395 build contract changed')
text=raw.decode()
# Isolate the server build from the optional, unverified graphical-client artifact.
text=text.split("client_classes=WORK/'client-classes'",1)[0]
text=once(text,"java_sources=[str(p) for p in sorted((ROOT/'native/overworld-r395').glob('*.java'))]+[str(light)]", "java_sources=[str(p) for p in sorted((ROOT/'native/overworld-r395').glob('*.java'))]+[str(p) for p in sorted((OUT/'r398-generated').glob('*.java'))]+[str(ROOT/'native/overworld-r38/NeverOverworldWaterPolicyR38.java'),str(light)]")
ast.parse(text);(OUT/'r398-generated-build.py').write_text(text)
sys.path.insert(0,str(source.parent))
exec(compile(text,str(source),'exec'),{'__name__':'__main__','__file__':str(source)})
report=json.loads((OUT/'build.json').read_text())
classes=report['changed_or_added_classes']
for name in (*SOURCES,'NeverOverworldWaterPolicyR38.java'):
 need('net/minecraft/world/level/chunk/'+name[:-5]+'.class' in classes,'Required class not actually compiled: '+name)
report.update({'experiment':'R398 full-chunk safety with R396 policy and opt-in R395 closure','full_chunk_guarded_entry_points':changes,'r396_policy_included':True,'ocean_closure_default_enabled':False,'production_accepted':False,'client_mod_included':False})
(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print('R398_BUILD',json.dumps(report),flush=True)
