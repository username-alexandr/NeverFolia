#!/usr/bin/env python3
"""Compose pinned executed deltas without inventing connector repairs.
Actual cart targets already exist in the original tavern_trader child pool.
Validate them and preserve every original NBT byte. Runtime still requires NPCs.
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
    raw=found[0].read_bytes();s.need(s.sha(raw)==want,'Wrong executed input '+name)
    return raw

def resource(kind,ident,suffix):
    parts=ident.split(':');s.need(len(parts)==2 and parts[0] and parts[1] and '..' not in parts[1] and not parts[1].startswith('/'),'Bad resource id')
    return 'data/'+parts[0]+'/'+kind+'/'+parts[1]+suffix

def joints(root):
    s.need('palettes' not in root,'Unreviewed multiple palettes')
    palette=root.get('palette');s.need(palette and palette[0]==9 and palette[1][0]==10,'Missing typed block palette')
    states=palette[1][1]
    for block in root.get('blocks',(9,(10,[])))[1][1]:
        state=block.get('state');s.need(state and state[0]==3 and type(state[1]) is int and 0<=state[1]<len(states),'Invalid palette index')
        if states[state[1]].get('Name')!=(8,'minecraft:jigsaw'):continue
        raw=block.get('nbt');s.need(raw and raw[0]==10,'Jigsaw lacks compound data')
        n=raw[1]
        s.need('id' not in n or n['id']==(8,'minecraft:jigsaw'),'Contradictory jigsaw NBT id')
        for key in ('name','target','pool'):s.need(n.get(key) and n[key][0]==8,'Jigsaw lacks '+key)
        yield block,n

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
        root=reader._nbt_parse(files[target])[2];names={n['name'][1] for _,n in joints(root)}
        rows.append({'template':target,'weight':weight,'names':sorted(names),'sha256':s.sha(files[target]),'entities':root.get('entities')})
    for entry in obj['elements']:
        w=entry['weight'];s.need(type(w) is int and w>0,'Unexpected child weight');element(entry['element'],w)
    return {n for row in rows for n in row['names']},rows

def validate_compatibility(target,names,rows):
    s.need(target in names,'No original child joint matches '+target)
    matching=[row for row in rows if target in row['names']]
    s.need(matching,'Missing compatible child evidence')
    # Name compatibility is necessary, not sufficient for actual placement.
    # Geometry/profession/NPC counts remain independently checked by Minecraft.
    for row in matching:
        entities=row.get('entities')
        s.need(entities and entities[0]==9 and entities[1][0]==10,'Matching child lacks entity list')
        payloads=[e.get('nbt',(10,{}))[1] for e in entities[1][1]]
        s.need(any(e.get('id')==(8,'minecraft:villager') for e in payloads),'Matching child does not contain an authored villager')
    return [row['template'] for row in matching]

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
    OUT.mkdir(exist_ok=True);report={'pass':False,'production_accepted':False};observed=[];cases=[]
    try:
        base=exact('inputs','NeverOverworld.zip',BASE);cart=exact('cart-input','NeverOverworld-R3914.zip',CART);swift=exact('swift-input','NeverOverworld-R3915.zip',SWIFT)
        exact('swift-input','server-r3915.jar',CORE)
        before,files,recovered=compose(base,cart,swift)
        reader=s.load('r3915_connector_nbt',ROOT/'scripts/build-never-overworld-external-structures-r19.py');pool_cache={}
        for path in sorted(files):
            if not path.startswith(PREFIX) or not path.endswith('.nbt'):continue
            model_name=path[len(PREFIX):-4];biome=next((b for b in BIOMES if model_name.endswith('_'+b)),None)
            if biome is None:continue
            role=model_name[:-len(biome)-1];root=reader._nbt_parse(files[path])[2];active=[]
            for block,n in joints(root):
                target=n['target'][1];pool=n['pool'][1]
                if 'tavern_villager' not in target:continue
                if pool not in pool_cache:pool_cache[pool]=pool_names(files,reader,pool)
                names,rows=pool_cache[pool]
                compatible=validate_compatibility(target,names,rows)
                observed.append({'cart':path,'position':block['pos'][1][1],'target':target,'pool':pool,'matches':True,'compatible_children':compatible,'nbt_id_present':'id' in n})
                active.append(target)
            if path in recovered or (role=='armorer' and biome in ('mangrove','pale','swamp')):
                s.need(len(active)==1 or (biome=='pale' and not active),'Unexpected NPC connector count in '+path)
                cases.append({'id':'nova_structures:tavern/tavern_event_trader_car_'+model_name,'role':role,'biome':biome,'expected_villagers':len(active),'target':'nova_structures:tavern_trader_car_'+biome,'root_size':root['size'][1][1]})
        s.need(len(cases)==25,'Missing cart fixture cases')
        for role in ('armorer','cartographer','cleric'):
            selected=[x for x in observed if x['cart']==PREFIX+role+'_mangrove.nbt']
            s.need(len(selected)==1 and selected[0]['matches'],'Mangrove compatibility not actually checked')
        # The previous "must edit mangrove" assertion was an unsupported premise:
        # the pinned input already has the required mangrove child connector.
        # Preserve valid data instead of manufacturing a change to satisfy it.
        fp=s.load('r3915_combined_fingerprint',ROOT/'scripts/fingerprint-never-overworld-pack.py')
        encoded=(json.dumps(fp.fingerprint_document(files),ensure_ascii=False,indent=2)+'\n').encode()
        for path in s.FP:files[path]=encoded
        output=s.write_zip(files);s.need(output==s.write_zip(files) and s.read_zip(output)==files,'Combined pack encoding is not repeatable')
        s.need(all(files[p]==v for p,v in before.items() if p not in {s.ENCHANT,*s.FP}),'Unrelated original resource changed')
        (OUT/'NeverOverworld-R3915-Combined.zip').write_bytes(output)
        report.update({'pass':True,'base_pack_sha256':BASE,'executed_cart_pack_sha256':CART,'swift_pack_sha256':SWIFT,'core_sha256':CORE,'output_sha256':s.sha(output),'added_templates':sorted(recovered),'preserved_original_entries':sum(files[p]==v for p,v in before.items()),'connector_edits':0,'matched_npc_connectors':len(observed),'scope':'Exact union of executed deltas with actual child compatibility; no speculative connector edits. Not all missing structures or natural spawn acceptance.'})
        print('COMBINED_CONTENT',json.dumps(report,ensure_ascii=False),flush=True)
    except Exception as e:report['error']=repr(e);raise
    finally:
        report.update({'repaired_templates':[],'connector_observations':observed,'cases':cases})
        (OUT/'combined-content.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
