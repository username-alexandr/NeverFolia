#!/usr/bin/env python3
"""Apply reviewed NPC-contract changes to the exact PR29 QA sources.
Only checkout text files change. No server/datapack bytes or worlds are edited.
All source identities and replacements are validated before writing any file.
"""
from pathlib import Path
import ast,difflib,hashlib,json
ROOT=Path(__file__).resolve().parent
EXPECTED={'combine_content.py':'770dd49648fce43c4f63f27b3117eab8497171ca','run_combined.py':'92f391366afffa11184f3c47a36663695e449765','R3915CartQa.java':'588c7b93ebc9305f6157b0d0b6b768664e99a508'}

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Source anchor count mismatch: '+repr(old[:100]))
    return text.replace(old,new,1)

def build_changes(original):
    result={}
    c=once(original['combine_content.py'],'import restore_swift as s\n','import restore_swift as s\nimport authored_npc as npc\n')
    old="""        entities=row.get('entities')
        s.need(entities and entities[0]==9 and entities[1][0]==10,'Matching child lacks entity list')
        payloads=[e.get('nbt',(10,{}))[1] for e in entities[1][1]]
        s.need(any(e.get('id')==(8,'minecraft:villager') for e in payloads),'Matching child does not contain an authored villager')
"""
    c=once(c,old,"        npc.entity_signature(row.get('entities'),required=True)\n")
    c=once(c,"'expected_villagers':len(active),","**npc.cart_contract(root,[(n['target'][1],pool_cache[n['pool'][1]][1]) for _,n in joints(root) if 'tavern_villager' in n['target'][1]]),")
    result['combine_content.py']=c
    r=once(original['run_combined.py'],'import combine_content as c\n','import combine_content as c\nimport authored_npc as npc\n')
    start=r.index('def validate_cases(cases):\n');end=r.index('def root_fixture(',start)
    r=r[:start]+"def validate_cases(cases):\n    return npc.validate_cases(cases,expected_ids())\n\ndef validate_cart(observed,nonce,cases):\n    return npc.validate_cart(observed,nonce,cases,expected_ids(),SEED)\n\n"+r[end:]
    result['run_combined.py']=r
    j=once(original['R3915CartQa.java'],'import net.minecraft.core.registries.Registries;','import net.minecraft.core.registries.Registries;\nimport net.minecraft.core.registries.BuiltInRegistries;')
    j=once(j,'var villagers=level.getEntitiesOfClass(LivingEntity.class,AREA,e->!e.isRemoved()&&e.getBukkitEntity() instanceof Villager);','var villagers=level.getEntitiesOfClass(LivingEntity.class,AREA,e->!e.isRemoved());')
    old='JsonArray npc=new JsonArray();for(var entity:villagers){JsonObject n=new JsonObject();n.addProperty("uuid",entity.getUUID().toString());n.addProperty("profession",((Villager)entity.getBukkitEntity()).getProfession().name());n.addProperty("position",entity.position().toString());npc.add(n);}'
    new='''JsonArray npc=new JsonArray();Map<String,Integer> counts=new TreeMap<>();
                    for(var entity:villagers){
                        String type=BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString();counts.merge(type,1,Integer::sum);
                        JsonObject n=new JsonObject();n.addProperty("uuid",entity.getUUID().toString());n.addProperty("type",type);
                        if(entity.getBukkitEntity() instanceof Villager v)n.addProperty("profession",v.getProfession().name());
                        n.addProperty("position",entity.position().toString());npc.add(n);
                    }
                    JsonObject observedTypes=new JsonObject();counts.forEach(observedTypes::addProperty);'''
    j=once(j,old,new)
    j=once(j,'int expected=c.get("expected_villagers").getAsInt();need(villagers.size()==expected,"NPC count "+id+" actual="+villagers.size()+" expected="+expected);','boolean matches=false;for(var expected:c.getAsJsonArray("expected_npcs")){if(expected.getAsJsonObject().equals(observedTypes))matches=true;}need(matches,"NPC species/count "+id+" actual="+observedTypes+" expected="+c.get("expected_npcs"));')
    j=once(j,'row.addProperty("observed_villagers",villagers.size());','row.add("observed_npcs",observedTypes);')
    j=once(j,'/** 22 restored models plus three source armorer carts with repaired aliases.','/** 22 restored models plus three unchanged source armorer carts.\n * NPC species/counts are derived from actual child NBT, including witches.')
    result['R3915CartQa.java']=j
    for name,text in result.items():
        if name.endswith('.py'):ast.parse(text,filename=name)
        if 'expected_villagers' in text or 'observed_villagers' in text:raise ValueError('Legacy villager-only contract remains: '+name)
    return result

def main():
    original={};raw_inputs={}
    for name,expected in EXPECTED.items():
        raw=(ROOT/name).read_bytes();actual=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
        if actual!=expected:raise ValueError('Unreviewed source version: '+name)
        raw_inputs[name]=raw;original[name]=raw.decode('utf-8')
    modified=build_changes(original)
    out=ROOT.parents[1]/'artifacts/authored-npc-source';out.mkdir(parents=True,exist_ok=False)
    records={}
    for name,text in modified.items():
        if (ROOT/name).read_bytes()!=raw_inputs[name]:raise ValueError('Source changed during preparation')
        (out/(name+'.before.txt')).write_bytes(raw_inputs[name])
        (out/name).write_text(text,encoding='utf-8')
        (out/(name+'.diff')).write_text(''.join(difflib.unified_diff(original[name].splitlines(True),text.splitlines(True),fromfile='a/'+name,tofile='b/'+name)),encoding='utf-8')
        records[name]={'input_blob':EXPECTED[name],'output_sha256':hashlib.sha256(text.encode()).hexdigest()}
    for name,text in modified.items():(ROOT/name).write_text(text,encoding='utf-8')
    (out/'transformation.json').write_text(json.dumps({'files':records,'datapack_changed':False,'server_changed':False},indent=2)+'\n')
    print('AUTHORED_NPC_CONTRACT_APPLIED',json.dumps(records),flush=True)
if __name__=='__main__':main()
