#!/usr/bin/env python3
"""Compose exact executed deltas. Connector spelling is only a static check;
actual NPC assembly must pass independently before this composition is accepted.
"""
from pathlib import Path
import json
import restore_swift as s
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts'
BASE=s.BASE
CART='9e0026a8c82c4242b438e06ce016d785aef1bf624d4dad13dea665d9dba20329'
SWIFT='1e935c1012aa0648b14aa3ab7bf84fd3e0bc43ead8e95ad9060316c428dc1046'
CORE='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
PREFIX='data/nova_structures/structure/tavern/tavern_event_trader_car_'
BIOMES=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')

def exact(folder,name,want):
    found=[p for p in Path(folder).rglob(name) if p.is_file()]
    s.need(len(found)==1,'Ambiguous input '+name)
    raw=found[0].read_bytes();actual=s.sha(raw)
    s.need(actual==want,'Wrong executed input '+name+' expected='+want+' actual='+actual)
    return raw

def resource(kind,ident,suffix):
    parts=ident.split(':');s.need(len(parts)==2 and parts[0] and parts[1] and '..' not in parts[1] and not parts[1].startswith('/'),'Bad resource id')
    return 'data/'+parts[0]+'/'+kind+'/'+parts[1]+suffix

def reviewed_carts():
    rows={PREFIX+role+'_'+biome+'.nbt':(role,biome) for role in ('cartographer','cleric') for biome in BIOMES}
    rows.update({PREFIX+'armorer_'+biome+'.nbt':('armorer',biome) for biome in ('mangrove','pale','swamp')})
    s.need(len(rows)==25,'Invalid mandatory cart inventory')
    return rows

def joints(root):
    s.need('palettes' not in root,'Unreviewed multiple palettes')
    for block in root.get('blocks',(9,(10,[])))[1][1]:
        n=block.get('nbt',(10,{}))[1]
        if n.get('id')==(8,'minecraft:jigsaw'):yield block,n

def detailed_joints(root):
    palette=root['palette'][1][1]
    return [{'position':b['pos'][1][1],'state':palette[b['state'][1]],'nbt':n} for b,n in joints(root)]

def pool_names(files,reader,ident):
    path=resource('worldgen/template_pool',ident,'.json');s.need(path in files,'Missing pool '+path)
    obj=json.loads(files[path]);rows=[]
    def element(e,weight):
        kind=e.get('element_type')
        if kind=='minecraft:empty_pool_element':return
        if kind=='minecraft:list_pool_element':
            for child in e['elements']:element(child,weight)
            return
        s.need(kind in ('minecraft:single_pool_element','minecraft:legacy_single_pool_element'),'Unreviewed child pool element '+str(kind))
        location=e.get('location');s.need(isinstance(location,str),'Inline template not reviewed')
        target=resource('structure',location,'.nbt');s.need(target in files,'Missing child '+target)
        root=reader._nbt_parse(files[target])[2]
        names={n['name'][1] for _,n in joints(root)}
        rows.append({'template':target,'weight':weight,'element':e,'names':sorted(names),'sha256':s.sha(files[target]),'size':root['size'],'joints':detailed_joints(root),'entities':root.get('entities')})
    for entry in obj['elements']:
        w=entry['weight'];s.need(type(w) is int and w>0,'Unexpected child weight');element(entry['element'],w)
    return {n for row in rows for n in row['names']},rows

def compose(base,cart,swift):
    a,b,c=map(s.read_zip,(base,cart,swift))
    expected={PREFIX+role+'_'+biome+'.nbt' for role in ('cartographer','cleric') for biome in BIOMES}
    s.need(set(b)-set(a)==expected and not set(a)-set(b),'Wrong cart addition set')
    s.need(all(b[p]==v for p,v in a.items() if p not in s.FP),'Cart artifact changed other original files')
    added={resource('function','nova_structures:swift_soar_'+str(i),'.mcfunction') for i in (1,2,3)}|{resource('predicate','nova_structures:'+p,'.json') for p in s.PREDICATES}
    s.need(set(c)-set(a)==added and not set(a)-set(c),'Wrong Swift addition set')
    s.need(all(c[p]==v for p,v in a.items() if p not in (*s.FP,s.ENCHANT)),'Swift artifact changed unrelated original resources')
    result=b.copy()
    for path in {s.ENCHANT}|added:result[path]=c[path]
    return a,result,expected

def main():
    OUT.mkdir(exist_ok=True);report={'pass':False,'production_accepted':False,'npc_assembly_accepted':False}
    observed=[];cases=[];inventory=[];pool_details={}
    report.update({'repaired_templates':[],'connector_observations':observed,'cases':cases,'cart_input_inventory':inventory,'child_pools':pool_details})
    try:
        base=exact('inputs','NeverOverworld.zip',BASE);cart=exact('cart-input','NeverOverworld-R3914.zip',CART);swift=exact('swift-input','NeverOverworld-R3915.zip',SWIFT)
        exact('swift-input','server-r3915.jar',CORE)
        before,files,recovered=compose(base,cart,swift);selected=reviewed_carts()
        report['required_cart_paths']=sorted(selected);report['missing_required_carts']=sorted(set(selected)-set(files))
        s.need(not report['missing_required_carts'],'Missing mandatory reviewed carts')
        s.need(recovered<=set(selected),'A restored cart is not covered')
        reader=s.load('r3915_connector_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
        emitted=set()
        for path,(role,biome) in sorted(selected.items()):
            root=reader._nbt_parse(files[path])[2];model_name=role+'_'+biome
            inventory.append({'path':path,'role':role,'biome':biome,'size':root['size'],'joints':detailed_joints(root),'entities':root.get('entities')})
            active=[]
            for block,n in joints(root):
                target=n.get('target',(8,''))[1];pool=n.get('pool',(8,''))[1]
                if 'tavern_villager' not in target:continue
                if pool not in pool_details:
                    _,pool_details[pool]=pool_names(files,reader,pool)
                rows=pool_details[pool];matching=[r for r in rows if target in r['names']]
                observed.append({'cart':path,'position':block['pos'][1][1],'target':target,'pool':pool,'matching_children':[r['template'] for r in matching]})
                s.need(matching,'Unresolved NPC target '+target+' in '+path)
                for row in matching:
                    if row['template'] not in emitted:
                        emitted.add(row['template']);print('CART_CHILD',json.dumps(row,ensure_ascii=False),flush=True)
                active.append(target)
            s.need(len(active)==(0 if biome=='pale' else 1),'Unexpected authored NPC connector count '+path)
            cases.append({'id':'nova_structures:tavern/tavern_event_trader_car_'+model_name,'role':role,'biome':biome,'expected_villagers':len(active),'target':'nova_structures:tavern_trader_car_'+biome,'root_size':root['size'][1][1]})
        s.need(len(cases)==25 and len(inventory)==25,'Incomplete mandatory inventory')
        # The executed scan proved all names resolve, contrary to the original
        # alias hypothesis. Do not force an unnecessary rename to satisfy it.
        # Actual JigsawPlacement and NPC assertions remain mandatory downstream.
        fp=s.load('r3915_combined_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
        encoded=(json.dumps(fp.fingerprint_document(files),ensure_ascii=False,indent=2)+'\n').encode()
        for path in s.FP:files[path]=encoded
        output=s.write_zip(files);s.need(output==s.write_zip(files) and s.read_zip(output)==files,'Combined ZIP roundtrip differs')
        s.need(all(files[p]==v for p,v in before.items() if p not in {s.ENCHANT,*s.FP}),'Unrelated original resources changed')
        (OUT/'NeverOverworld-R3915-Combined.zip').write_bytes(output)
        report.update({'pass':True,'base_pack_sha256':BASE,'executed_cart_pack_sha256':CART,'swift_pack_sha256':SWIFT,'core_sha256':CORE,'output_sha256':s.sha(output),'added_templates':sorted(recovered),'preserved_original_entries':sum(files[p]==v for p,v in before.items()),'connector_spelling_mismatches':0,'scope':'Cumulative pack composition and exact connector inventory, not successful NPC assembly. Strict runtime remains required.'})
        print('COMBINED_CONTENT',json.dumps({k:v for k,v in report.items() if k not in ('connector_observations','cases','cart_input_inventory','child_pools')},ensure_ascii=False),flush=True)
    except Exception as e:report['error']=repr(e);raise
    finally:(OUT/'combined-content.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
