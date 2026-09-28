#!/usr/bin/env python3
"""Exact NPC contracts for pinned cart templates. Never mutates datapack bytes.
Supported authored NPCs are villagers and witches. Unknown entity kinds, empty
required children, malformed NBT and ambiguous metadata fail rather than relax
an expected count. The runtime may match only a full source-derived signature.
"""
from collections import Counter
import json
import re
import uuid

KINDS=frozenset(('minecraft:villager','minecraft:witch'))
ROLES=frozenset(('cartographer','cleric','armorer'))

def need(ok,message):
    if not ok:raise ValueError(message)

def typed(value,tag,description):
    need(isinstance(value,(tuple,list)) and len(value)==2 and value[0]==tag,'Bad NBT '+description)
    return value[1]

def entity_signature(value,required=False):
    if value is None:
        need(not required,'Required child has no entity list')
        return {}
    subtype,payload=typed(value,9,'entities list')
    need(isinstance(payload,list) and subtype in (0,10),'Bad entity compound list')
    need(subtype==10 or not payload,'TAG_End cannot contain entities')
    counts=Counter()
    for entry in payload:
        need(isinstance(entry,dict),'Bad entity record')
        nbt=typed(entry.get('nbt'),10,'entity payload')
        need(isinstance(nbt,dict),'Bad entity NBT compound')
        ident=typed(nbt.get('id'),8,'entity identifier')
        need(ident in KINDS,'Unreviewed authored NPC kind: '+str(ident))
        if 'Passengers' in nbt:
            _,passengers=typed(nbt['Passengers'],9,'passengers')
            need(not passengers,'Passenger NPC graph requires separate review')
        counts[ident]+=1
    need(not required or sum(counts.values())>0,'Required child contains no authored NPC')
    return dict(sorted(counts.items()))

def compatible(target,names,rows):
    need(target in names,'No original child joint matches '+target)
    matching=[r for r in rows if target in r['names']]
    need(bool(matching),'Missing compatible child evidence')
    for row in matching:entity_signature(row.get('entities'),required=True)
    return matching

def cart_contract(root,links):
    """links contains (target, rows) selected by REAL palette jigsaws."""
    root_sig=entity_signature(root.get('entities'))
    need(len(links)<=1,'Multiple NPC joints require graph-combination review')
    sources=[];variants=[]
    if not links:
        variants=[root_sig]
    else:
        target,rows=links[0]
        matching=compatible(target,{n for r in rows for n in r['names']},rows)
        for row in matching:
            child=entity_signature(row.get('entities'),required=True)
            signature=dict(sorted((Counter(root_sig)+Counter(child)).items()))
            variants.append(signature)
            sources.append({'template':row['template'],'sha256':row['sha256'],'target':target,'root_npcs':root_sig,'child_npcs':child,'combined_npcs':signature})
    unique={json.dumps(v,sort_keys=True):v for v in variants}
    return {'expected_npcs':[unique[k] for k in sorted(unique)],'npc_sources':sources}

def validate_cases(cases,expected_ids):
    need(isinstance(cases,list) and len(cases)==len(expected_ids),'Incomplete input case list')
    ids=[r.get('id') for r in cases]
    need(len(set(ids))==len(ids) and set(ids)==set(expected_ids),'Wrong/duplicate input cases')
    for row in cases:
        need(row.get('role') in ROLES,'Unknown role')
        choices=row.get('expected_npcs')
        need(isinstance(choices,list) and bool(choices),'Missing authored NPC signatures')
        need(len({json.dumps(s,sort_keys=True) for s in choices})==len(choices),'Duplicate NPC signatures')
        for signature in choices:
            need(isinstance(signature,dict),'NPC signature is not a mapping')
            need(all(k in KINDS and type(v) is int and v>0 for k,v in signature.items()),'Invalid authored NPC kind/count')
            need(sum(signature.values())<=8,'Unexpected cart population')
            need(bool(signature) or row.get('biome')=='pale','Only explicitly reviewed childless pale carts may be empty')

def validate_cart(observed,nonce,cases,expected_ids,seed):
    validate_cases(cases,expected_ids)
    need(observed.get('pass') is True and observed.get('nonce')==nonce and observed.get('seed')==seed,'Not a fresh successful cart result')
    rows=observed.get('checks',[])
    need(observed.get('completed')==len(cases) and len(rows)==len(cases),'Incomplete actual cart coverage')
    need([r.get('id') for r in rows]==[r['id'] for r in cases],'Actual variant order/identity changed')
    for actual,want in zip(rows,cases):
        need(actual.get('pass') is True,'A cart check failed')
        for key in ('role','biome','expected_npcs','target','root_size'):
            need(actual.get(key)==want[key],'Fixture metadata changed: '+key)
        need(actual.get('workstations')==1 and actual.get('remaining_jigsaws')==0 and actual.get('nonair_cart_blocks',0)>8,'Incomplete assembly')
        observed_types=actual.get('observed_npcs')
        need(isinstance(observed_types,dict) and all(k in KINDS and type(v) is int and v>0 for k,v in observed_types.items()),'Invalid observed type/count')
        need(observed_types in want['expected_npcs'],'Actual NPC species/count does not match any authored child')
        npcs=actual.get('npc_observations')
        need(isinstance(npcs,list),'Missing NPC observations')
        ids=[];kinds=Counter()
        for npc in npcs:
            need(npc.get('type') in KINDS,'Unexpected live NPC')
            try:ident=str(uuid.UUID(npc.get('uuid','')))
            except (ValueError,AttributeError,TypeError):raise ValueError('Invalid live UUID')
            ids.append(ident);kinds[npc['type']]+=1
        need(len(ids)==len(set(ids)) and dict(kinds)==observed_types,'Duplicate/missing live NPC evidence')
    teardown=observed.get('entity_teardowns',[])
    need(len(teardown)==len(cases) and [r.get('next_case') for r in teardown]==list(range(len(cases))),'Missing case-isolation barriers')
    need(all(r.get('live_after_barrier')==0 for r in teardown),'Prior NPC contaminated a fixture')
