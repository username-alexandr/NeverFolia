#!/usr/bin/env python3
"""Reconstruct missing cleric/cartographer biome carts using a proven shared recipe.
An existing furnace's lit flag is not transferable to unrelated workstations.
All such reference-only differences are reported explicitly; no other voxel,
property, block NBT or entity mismatch is accepted.
"""
from pathlib import Path
import copy,hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'cart-recovery'
FURNACES={'minecraft:furnace','minecraft:blast_furnace','minecraft:smoker'}
LIT_PATH=('blocks',(3,2,1),'state','Properties',1,'lit',1)
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
    OUT.mkdir(exist_ok=False);recipe=load('cart_recipe_r40',ROOT/'qa/field-r394/build_candidate.py');nbt=load('cart_nbt40',ROOT/'scripts/build-never-overworld-external-structures-r19.py');fp=load('cart_fp40',ROOT/'scripts/fingerprint-never-overworld-pack.py')
    source=ROOT/'baseline/world/datapacks/NeverOverworld.zip';report={'pass':False,'production_accepted':False};output=OUT/'NeverOverworld-cart-candidate.zip'
    try:
        recipe.need(hashlib.sha256(source.read_bytes()).hexdigest()==recipe.SOURCE,'Wrong exact input pack')
        with zipfile.ZipFile(source) as z:
            recipe.need(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),'Invalid source ZIP');files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
        original=files.copy();recipe.need(len(files)==8007,'Unexpected input resource count')
        recipe.need(json.loads(files[recipe.FINGERPRINTS[0]])==fp.fingerprint_document(files),'Input fingerprint mismatch')
        parsed={role:nbt._nbt_parse(files[recipe.PREFIX+role+'.nbt']) for role in recipe.ROLES+recipe.RECOVER}
        for role in recipe.RECOVER:
            recipe.need(recipe.sha(files[recipe.PREFIX+role+'.nbt'])==recipe.BASE_HASHES[role],'Profession base changed');recipe.validate_cart(parsed[role][2])
        proofs=[];added=[];reference_exceptions=[]
        for biome in recipe.BIOMES:
            base=recipe.model(parsed['armorer'][2]);reference=recipe.model(nbt._nbt_parse(files[recipe.PREFIX+'armorer_'+biome+'.nbt'])[2]);ops=[]
            for path,before,after in recipe.changes(base,reference):
                if path==LIT_PATH:
                    name=base['blocks'][(3,2,1)]['state']['Name'][1]
                    recipe.need(name in FURNACES and before in ('false','true') and after in ('false','true'),'Unreviewed workstation property')
                    continue
                recipe.need(recipe.allowed(path),'Unapproved shared biome field '+repr(path));ops.append((path,before,after))
            for role in recipe.ROLES:
                root=parsed[role][2];desired=recipe.transform(recipe.model(root),ops)
                expected=recipe.model(nbt._nbt_parse(files[recipe.PREFIX+role+'_'+biome+'.nbt'])[2])
                differences=recipe.changes(desired,expected)
                for path,before,after in differences:
                    recipe.need(path==LIT_PATH,'Nonuniform biome recipe '+role+'_'+biome+': '+repr(differences[:8]))
                    a=desired['blocks'][(3,2,1)]['state'];b=expected['blocks'][(3,2,1)]['state']
                    recipe.need(a['Name']==b['Name'] and a['Name'][1] in FURNACES and before in ('true','false') and after in ('true','false'),'Mismatch is not the preserved furnace lit state')
                    reference_exceptions.append({'role':role,'biome':biome,'position':[3,2,1],'block':a['Name'][1],'property':'lit','retained_base':before,'reference':after})
                rebuilt=recipe.rebuild(root,desired);recipe.validate_cart(rebuilt,biome)
                proofs.append({'role':role,'biome':biome,'all_other_voxels_properties_and_typed_nbt_match':True,'workstation_lit_differences':len(differences)})
            for role in recipe.RECOVER:
                compression,name,root=parsed[role];desired=recipe.transform(recipe.model(root),ops);rebuilt=recipe.rebuild(root,desired);recipe.validate_cart(rebuilt,biome)
                path=recipe.PREFIX+role+'_'+biome+'.nbt';recipe.need(path not in files,'Would overwrite existing template')
                payload=recipe.encode(nbt,compression,name,rebuilt);files[path]=payload
                recipe.need(rebuilt['entities']==root['entities'],'Profession entities changed')
                # The workstation is preserved exactly, not borrowed from an armorer.
                pos=(3,2,1);recipe.need(desired['blocks'][pos]==recipe.model(root)['blocks'][pos],'Profession workstation changed')
                added.append({'path':path,'sha256':recipe.sha(payload),'role':role,'biome':biome,'size':rebuilt['size'][1][1],'source':recipe.PREFIX+role+'.nbt','preserved_workstation':True})
        recipe.need(len(added)==22 and len(proofs)==121,'Incomplete recipe coverage')
        doc=fp.fingerprint_document(files);encoded=(json.dumps(doc,indent=2,ensure_ascii=False)+'\n').encode()
        for name in recipe.FINGERPRINTS:files[name]=encoded
        recipe.need(all(files[n]==data for n,data in original.items() if n not in recipe.FINGERPRINTS),'Original resource changed')
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for n,data in sorted(files.items()):
                info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,data,compresslevel=9)
        with zipfile.ZipFile(output) as z:recipe.need(z.testzip() is None and len(z.namelist())==8029,'Invalid candidate archive')
        audit=load('cart_audit40',ROOT/'scripts/audit-neveroverworld-r39-resources.py');before=audit.audit_files(ROOT/'baseline/server.jar',source);after=audit.audit_files(ROOT/'baseline/server.jar',output)
        old={(r['kind'],r['id']) for r in before['missing']};new={(r['kind'],r['id']) for r in after['missing']}
        wanted={('template','nova_structures:tavern/tavern_event_trader_car_'+role+'_'+biome) for role in recipe.RECOVER for biome in recipe.BIOMES}
        recipe.need(old-new==wanted and not new-old,'Unexpected graph changes')
        (OUT/'resources-before.json').write_text(json.dumps(before,indent=2)+'\n');(OUT/'resources-after.json').write_text(json.dumps(after,indent=2)+'\n')
        report={'pass':True,'production_accepted':False,'source_sha256':recipe.SOURCE,'output_sha256':recipe.sha(output.read_bytes()),'added':added,'validated_existing_variants':proofs,'reference_only_lit_differences':reference_exceptions,'before_counts':before['counts'],'after_counts':after['counts'],'scope':'Shared biome material and connector recipe proved on 121 original variants. Only listed furnace lit differences excluded; source workstation states preserved. Actual jigsaw runtime still required.'}
    except Exception as error:
        report={'pass':False,'error':repr(error),'production_accepted':False}
        if output.exists():output.rename(OUT/'REJECTED-candidate.zip')
    (OUT/'cart-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R40_CART_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('added','validated_existing_variants')}),flush=True)
    if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
