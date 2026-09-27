#!/usr/bin/env python3
"""Reuse the semantic biome recipe, replacing obsolete assumed cart dimensions.
Nothing is published unless all existing role/biome templates match the recipe.
"""
from pathlib import Path
import importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'cart-recovery'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    OUT.mkdir(exist_ok=False)
    recipe=load('cart_recipe_r40',ROOT/'qa/field-r394/build_candidate.py')
    nbt=load('cart_nbt_r40',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    source=ROOT/'baseline/world/datapacks/NeverOverworld.zip';dimensions={};reference_jigs={}
    with zipfile.ZipFile(source) as z:
        for role in recipe.ROLES+recipe.RECOVER:
            name=recipe.PREFIX+role+'.nbt';root=nbt._nbt_parse(z.read(name))[2]
            dimensions[role]=root['size'];jigs=[]
            for block in root['blocks'][1][1]:
                entry=block.get('nbt',(10,{}))[1]
                if entry.get('id')==(8,'minecraft:jigsaw'):jigs.append({'pos':block['pos'][1][1],'values':entry})
            reference_jigs[role]=jigs
        example=nbt._nbt_parse(z.read(recipe.PREFIX+'armorer_oak.nbt'))[2]
        print('R40_CART_BASE_DIMENSIONS',json.dumps(dimensions),flush=True)
        print('R40_CART_REFERENCE_VARIANT_SIZE',example['size'],flush=True)
        print('R40_CART_PARENT_JIGSAWS',json.dumps(reference_jigs),flush=True)
    def validate(root,biome=None):
        size=root.get('size');recipe.need(size is not None and size[0]==9 and size[1][0]==3 and len(size[1][1])==3,'Invalid template dimensions')
        dims=size[1][1];recipe.need(all(type(v)==int and 1<=v<=64 for v in dims),'Unbounded template')
        model=recipe.model(root)
        for pos,record in model['blocks'].items():
            recipe.need(all(0<=pos[i]<dims[i] for i in range(3)),'Block outside template')
            if record.get('nbt',(10,{}))[1].get('id')==(8,'minecraft:jigsaw'):
                for k in ('name','target','pool'):
                    value=record['nbt'][1].get(k);recipe.need(value is not None and value[0]==8 and ':' in value[1],'Invalid connector '+k)
        # Geometric and NBT correctness is established by the complete 121-template
        # equality test, not a stale fixed size or a guessed connector label.
    recipe.validate_cart=validate
    report={'pass':False,'production_accepted':False}
    try:
        output=OUT/'NeverOverworld-cart-candidate.zip'
        report=recipe.build(source,output)
        with zipfile.ZipFile(output) as z:
            for entry in report['added_templates']:
                root=nbt._nbt_parse(z.read(entry['path']))[2]
                entry['size']=root['size'][1][1];entry['direct_entities']=len(root.get('entities',(9,(10,[])))[1][1])
        audit=load('cart_audit40',ROOT/'scripts/audit-neveroverworld-r39-resources.py')
        before=audit.audit_files(ROOT/'baseline/server.jar',source);after=audit.audit_files(ROOT/'baseline/server.jar',output)
        old={(x['kind'],x['id']) for x in before['missing']};new={(x['kind'],x['id']) for x in after['missing']}
        wanted={('template','nova_structures:tavern/tavern_event_trader_car_'+role+'_'+biome) for role in recipe.RECOVER for biome in recipe.BIOMES}
        recipe.need(old-new==wanted and not new-old,'Unexpected resource graph delta')
        report['before_counts']=before['counts'];report['after_counts']=after['counts'];report['scope']='22 reconstructed variants; exact voxel and typed-NBT equivalence on all 121 existing variants; actual template dimensions retained; runtime not yet accepted.'
        (OUT/'resources-before.json').write_text(json.dumps(before,indent=2)+'\n');(OUT/'resources-after.json').write_text(json.dumps(after,indent=2)+'\n')
    except Exception as error:
        report={'pass':False,'error':repr(error),'production_accepted':False}
        # A failed proof must not leave an installable candidate beside the report.
        candidate=OUT/'NeverOverworld-cart-candidate.zip'
        if candidate.exists():candidate.rename(OUT/'REJECTED-candidate.zip')
    (OUT/'cart-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R40_CART_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('added_templates','validated_existing_variants','biome_transformations')}),flush=True)
    if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
