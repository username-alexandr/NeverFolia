#!/usr/bin/env python3
"""Compose exact executed deltas and repair only reviewed NPC connector aliases.
A mandatory explicit cart inventory prevents an empty scan from looking valid.
"""
from pathlib import Path
import copy,json
import restore_swift as s
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts'
BASE=s.BASE
CART='9e0026a8c82c4242b438e06ce016d785aef1bf624d4dad13dea665d9dba20329'
SWIFT='1e935c1012aa0648b14aa3ab7bf84fd3e0bc43ead8e95ad9060316c428dc1046'
CORE='845d0e90fcbe0fbebad7a613aa9934f608cce64a9d41abdfdf012e39e21c1d40'
PREFIX='data/nova_structures/structure/tavern/tavern_event_trader_car_'
BIOMES=('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')
ALIASES={'nova_structures:tavern_villager_'+b for b in ('mangrove','pale','swamp')}
CANONICAL='nova_structures:tavern_villager_swamp'
CANONICAL_POOL='nova_structures:tavern/tavern_villager_swamp'

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
    rows={PREFIX+role+'_'+biome+'.nbt':(role,biome)
          for role in ('cartographer','cleric') for biome in BIOMES}
    rows.update({PREFIX+'armorer_'+biome+'.nbt':('armorer',biome)
                 for biome in ('mangrove','pale','swamp')})
    s.need(len(rows)==25,'Invalid mandatory cart inventory')
    return rows

def joints(root):
    s.need('palettes' not in root,'Unreviewed multiple palettes')
    for block in root.get('blocks',(9,(10,[])))[1][1]:
        n=block.get('nbt',(10,{}))[1]
        if n.get('id')==(8,'minecraft:jigsaw'):yield block,n

def pool_names(files,reader,ident):
    path=resource('worldgen/template_pool',ident,'.json')
    s.need(path in files,'Missing pool '+path)
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
        rows.append({'template':target,'weight':weight,'names':sorted(names),'sha256':s.sha(files[target]),'entities':root.get('entities')})
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
    OUT.mkdir(exist_ok=True);report={'pass':False,'production_accepted':False}
    repaired=[];observed=[];cases=[];inventory=[]
    report.update({'repaired_templates':repaired,'connector_observations':observed,'cases':cases,'cart_input_inventory':inventory})
    try:
        base=exact('inputs','NeverOverworld.zip',BASE);cart=exact('cart-input','NeverOverworld-R3914.zip',CART);swift=exact('swift-input','NeverOverworld-R3915.zip',SWIFT)
        exact('swift-input','server-r3915.jar',CORE)
        before,files,recovered=compose(base,cart,swift)
        selected=reviewed_carts()
        report['required_cart_paths']=sorted(selected)
        report['missing_required_carts']=sorted(set(selected)-set(files))
        print('REQUIRED_CART_INVENTORY',json.dumps({'required':sorted(selected),'missing':report['missing_required_carts'],'pack_entries':len(files)}),flush=True)
        s.need(not report['missing_required_carts'],'Missing reviewed carts; no suffix-based skipping is allowed')
        s.need(recovered<=set(selected),'A restored cart is not covered')
        reader=s.load('r3915_connector_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
        for path,(role,biome) in sorted(selected.items()):
            model_name=role+'_'+biome
            compressed,name,root=reader._nbt_parse(files[path]);original=copy.deepcopy(root);changes=[]
            inv={'path':path,'role':role,'biome':biome,'root_keys':sorted(root),'joints':[{'pos':b.get('pos'),'nbt':n} for b,n in joints(root)]}
            inventory.append(inv);print('CART_INPUT',json.dumps(inv,ensure_ascii=False),flush=True)
            for block,n in joints(root):
                target=n.get('target',(8,''))[1];pool=n.get('pool',(8,''))[1]
                if 'tavern_villager' not in target:continue
                names,rows=pool_names(files,reader,pool)
                observation={'cart':path,'position':block['pos'][1][1],'target':target,'pool':pool,'available_names':sorted(names),'matches':target in names}
                observed.append(observation);print('CART_CONNECTOR',json.dumps(observation,ensure_ascii=False),flush=True)
                if target in names:continue
                s.need(biome in ('mangrove','pale','swamp') and target in ALIASES,'Unreviewed connector mismatch '+json.dumps(observation))
                new_pool=pool
                if CANONICAL not in names:
                    s.need(pool in ('nova_structures:tavern/tavern_villager_mangrove',CANONICAL_POOL),'Unreviewed pool alias '+pool)
                    names,rows=pool_names(files,reader,CANONICAL_POOL);new_pool=CANONICAL_POOL
                s.need(CANONICAL in names,'Canonical swamp connector absent')
                compatible=[r for r in rows if CANONICAL in r['names']]
                s.need(compatible,'No matching NPC template')
                for row in compatible:
                    entities=row['entities'];s.need(entities and entities[0]==9,'Missing NPC entities')
                    payloads=[e.get('nbt',(10,{}))[1] for e in entities[1][1]]
                    s.need(any(e.get('id')==(8,'minecraft:villager') and e.get('VillagerData',(10,{}))[1].get('type')==(8,'minecraft:swamp') for e in payloads),'Target does not contain an authored swamp villager')
                changes.append({'position':block['pos'][1][1],'old_target':target,'new_target':CANONICAL,'old_pool':pool,'new_pool':new_pool,'compatible_children':[r['template'] for r in compatible]})
                n['target']=(8,CANONICAL);n['pool']=(8,new_pool)
            if changes:
                restored=copy.deepcopy(root)
                for change in changes:
                    matches=[n for b,n in joints(restored) if b['pos'][1][1]==change['position']]
                    s.need(len(matches)==1,'Ambiguous connector position');matches[0]['target']=(8,change['old_target']);matches[0]['pool']=(8,change['old_pool'])
                s.need(restored==original,'Unrelated NBT fields changed')
                raw=reader._nbt_encode(compressed,name,root);s.need(reader._nbt_parse(raw)==(compressed,name,root),'NBT serialization changed data')
                repaired.append({'path':path,'old_sha256':s.sha(files[path]),'sha256':s.sha(raw),'changes':changes});files[path]=raw
            active=[]
            for block,n in joints(root):
                if 'tavern_villager' not in n.get('target',(8,''))[1]:continue
                names,rows=pool_names(files,reader,n['pool'][1]);s.need(n['target'][1] in names,'Candidate still has mismatched NPC joint')
                active.append(n['target'][1])
            s.need(len(active)==(0 if biome=='pale' else 1),'Unexpected NPC connector count in '+path)
            cases.append({'id':'nova_structures:tavern/tavern_event_trader_car_'+model_name,'role':role,'biome':biome,'expected_villagers':len(active),'target':'nova_structures:tavern_trader_car_'+biome,'root_size':root['size'][1][1]})
        print('CART_SCAN_SUMMARY',json.dumps({'selected':len(inventory),'observed':len(observed),'repaired':len(repaired),'cases':len(cases)}),flush=True)
        s.need(repaired and any(p['path'].endswith('_mangrove.nbt') for p in repaired),'Known mangrove bug not fixed')
        s.need(len(cases)==25 and len(inventory)==25,'Missing cart fixture coverage')
        fp=s.load('r3915_combined_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
        encoded=(json.dumps(fp.fingerprint_document(files),ensure_ascii=False,indent=2)+'\n').encode()
        for path in s.FP:files[path]=encoded
        output=s.write_zip(files);s.need(output==s.write_zip(files) and s.read_zip(output)==files,'Combined pack encoding is not repeatable')
        allowed={p['path'] for p in repaired}|{s.ENCHANT,*s.FP}
        s.need(all(files[p]==v for p,v in before.items() if p not in allowed),'Unrelated original resource changed')
        (OUT/'NeverOverworld-R3915-Combined.zip').write_bytes(output)
        report.update({'pass':True,'base_pack_sha256':BASE,'executed_cart_pack_sha256':CART,'swift_pack_sha256':SWIFT,'core_sha256':CORE,'output_sha256':s.sha(output),'added_templates':sorted(recovered),'preserved_original_entries':sum(files[p]==v for p,v in before.items()),'scope':'Exact executed delta union and reviewed NPC connector repairs. Remaining templates and full natural spawn not accepted.'})
        print('COMBINED_CONTENT',json.dumps({k:v for k,v in report.items() if k not in ('connector_observations','cases','cart_input_inventory')},ensure_ascii=False),flush=True)
    except Exception as e:report['error']=repr(e);raise
    finally:(OUT/'combined-content.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
