"""Exact-version function bridge and optional location membership; no NBT edits.

Native commands are finite, entity-scoped operations, not globally re-enabled
Folia data/tag/item/scoreboard/function dispatchers. A native runtime is required.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'worldgen-spec/never-nether-dnt-r6.json'
SOURCE_SHA = '4096cd6372e0f244efa0e85c4d884bd85afe665a84a050280acd483b3222b4f9'
PREFIX = 'neverfolia:dnt '
LIMIT_TAG = 'neverfolia.dnt_minions_limit'


def transform_function(name: str, text: str) -> str:
    """Transform only a known function, after the caller verifies its exact hash."""
    if name.startswith('ghasted_fireball_'):
        level = name.rsplit('_', 1)[1]
        if level not in {'1', '2', '3'}: raise ValueError('Unknown fireball level')
        return '# R6: spawn/copy/retire as one owning-region operation.\n' + PREFIX + 'fireball_' + level + '\n'
    substitutions = {}
    if name == 'ghast_boss_fireball_possess':
        substitutions['data remove entity @n[type=minecraft:fireball,distance=..45] Owner'] = PREFIX+'clear_fireball_owner'
    elif name == 'ghast_boss_summon_child':
        substitutions['scoreboard players add @s dnt_boss_minion 1'] = PREFIX+'minion_increment'
    elif name == 'hydro_veil_heal':
        substitutions['data modify entity @s active_effects append value {id:"minecraft:regeneration",amplifier:6,duration:1,show_particles:0b}'] = PREFIX+'regenerate'
    elif name == 'jockey/make_drowned_into_jockey':
        substitutions['item replace entity @s saddle with air'] = PREFIX+'clear_saddle'
    elif name.startswith('swift_soar_') and name.rsplit('_',1)[1] in {'1','2','3'}:
        substitutions['tag @s add sprinting'] = PREFIX+'sprint_on'
        substitutions['tag @s remove sprinting'] = PREFIX+'sprint_off'
    elif name == 'quest/saddle_trade_checker':
        for level in range(2,6):
            substitutions[f'function nova_structures:quest/add_trade_lv{level}'] = PREFIX+f'call_trade_{level}'
    elif name.startswith('quest/add_trade_lv') and name[-1] in '2345':
        level=name[-1]
        suffix={'2':'','3':'_uncommon','4':'_rare','5':'_epic'}[level]
        substitutions['loot replace entity @s weapon.mainhand loot nova_structures:villagers/villager_emerald_counts'] = PREFIX+'loot_emeralds'
        substitutions['loot replace entity @s weapon.mainhand loot nova_structures:villagers/tavern_quest'+suffix] = PREFIX+'loot_chart_'+level
        substitutions['data modify entity @s Offers.Recipes prepend value {buyB:{id:"minecraft:compass",count:1},buy:{id:"minecraft:emerald",count:14},sell:{id:"minecraft:paper",count:1},maxUses:1}'] = PREFIX+'offer_prepend'
        substitutions['data modify entity @s Offers.Recipes[0].buy merge from entity @s equipment.mainhand'] = PREFIX+'offer_buy'
        substitutions['data modify entity @s Offers.Recipes[0].sell merge from entity @s equipment.mainhand'] = PREFIX+'offer_sell'
        substitutions[f'tag @s add trade{level}added'] = PREFIX+f'trade_{level}_added'
        substitutions['item replace entity @s saddle with air'] = PREFIX+'clear_saddle'
    else:
        raise ValueError('Unknown function repair: '+name)
    for old,new in substitutions.items():
        expected=2 if old=='tag @s remove sprinting' else 1
        if text.count(old)!=expected:raise ValueError('Changed function contract: '+name+' / '+old)
        text=text.replace(old,new)
    return text


def optional_locations(value: dict) -> tuple[dict, dict[PurePosixPath, bytes]]:
    """Absent optional structures mean non-membership, not invented structures.

    Preserve every loot entry, weight and condition. With no Overworld taverns
    registered, the existing inverted all-taverns branch remains the fallback.
    """
    value=copy.deepcopy(value);tags={};replacements=0
    allowed={'nova_structures:tavern_'+wood for wood in ('acacia','birch','cherry','dark_oak','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp')}
    def visit(obj):
        nonlocal replacements
        if isinstance(obj,dict):
            loc=obj.get('location')
            if isinstance(loc,dict) and 'structures' in loc:
                ids=loc['structures']; ids=[ids] if isinstance(ids,str) else ids
                if not isinstance(ids,list) or not ids or not set(ids)<=allowed:raise ValueError('Unexpected optional location set')
                label='all' if len(ids)>1 else ids[0].split('tavern_',1)[1]
                ident='neverfolia:never_nether/optional_taverns/'+label
                path=PurePosixPath('data/neverfolia/tags/worldgen/structure/never_nether/optional_taverns/'+label+'.json')
                tags[path]=(json.dumps({'replace':False,'values':[{'id':i,'required':False} for i in ids]},indent=2)+'\n').encode()
                loc['structures']='#'+ident;replacements+=1
            for child in obj.values():visit(child)
        elif isinstance(obj,list):
            for child in obj:visit(child)
    visit(value)
    if replacements!=13 or len(tags)!=13:raise ValueError('Expected exactly 13 tavern membership predicates')
    return value,tags


def local_minion_limit(value: dict) -> dict:
    value=copy.deepcopy(value);count=0
    def visit(obj):
        nonlocal count
        if isinstance(obj,dict):
            if obj.get('condition')=='minecraft:entity_scores':
                if obj!={'condition':'minecraft:entity_scores','entity':'this','scores':{'dnt_boss_minion':{'min':7}}}:raise ValueError('Changed minion-score contract')
                obj.clear();obj.update({'condition':'minecraft:entity_properties','entity':'this','predicate':{'nbt':'{Tags:["'+LIMIT_TAG+'"]}'}});count+=1
            for child in obj.values():visit(child)
        elif isinstance(obj,list):
            for child in obj:visit(child)
    visit(value)
    if count!=1:raise ValueError('Expected one minion threshold')
    return value


def validate_trade_loot(archive, profile: dict) -> None:
    """The native loot actions cannot inherit unreviewed world-changing effects."""
    allowed_functions={'minecraft:set_count','minecraft:set_components'}
    allowed_conditions={'minecraft:inverted','minecraft:entity_properties','minecraft:any_of'}
    def visit(value):
        if isinstance(value,dict):
            if 'random_sequence' in value:raise ValueError('Shared loot sequence is not supported by the local bridge')
            function=value.get('function');condition=value.get('condition')
            if function is not None and function not in allowed_functions:raise ValueError('Unreviewed trade loot function: '+str(function))
            if condition is not None and condition not in allowed_conditions:raise ValueError('Unreviewed trade condition: '+str(condition))
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    for path,expected in profile['trade_loot_hashes'].items():
        raw=archive.entries.get(PurePosixPath(path))
        if raw is None or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Trade loot contract mismatch: '+path)
        visit(json.loads(raw))


def apply_dnt(archive) -> None:
    profile=json.loads(PROFILE.read_text())
    if archive.sha256!=SOURCE_SHA or profile['source_sha256']!=SOURCE_SHA:raise ValueError('D&T R6 source mismatch')
    validate_trade_loot(archive,profile)
    staged={}; changes=[]
    for raw_path,expected in profile['contract_hashes'].items():
        path=PurePosixPath(raw_path);payload=archive.entries.get(path)
        if payload is None or hashlib.sha256(payload).hexdigest()!=expected:raise ValueError('D&T R6 contract mismatch: '+str(path))
        if path.suffix=='.mcfunction':
            name='/'.join(path.parts[3:])[:-11]
            converted=transform_function(name,payload.decode()).encode()
        elif path.parts[2]=='enchantment':
            converted=(json.dumps(local_minion_limit(json.loads(payload)),indent=2)+'\n').encode()
        else:
            obj,tags=optional_locations(json.loads(payload))
            for tag in tags:
                if tag in archive.entries or tag in staged:raise ValueError('Optional tag would overwrite: '+str(tag))
            staged.update(tags)
            converted=(json.dumps(obj,indent=2)+'\n').encode()
        staged[path]=converted
        changes.append({'resource':str(path),'original_sha256':expected,'output_sha256':hashlib.sha256(converted).hexdigest()})
    for path,payload in staged.items():
        archive.entries[path]=payload;archive.decoded.pop(path,None)
        archive.provenance[path]='neverfolia-r6/'+str(path)
    archive.optional_external_structures.update(
        member['id'] for path,payload in staged.items()
        if str(path).startswith('data/neverfolia/tags/worldgen/structure/')
        for member in json.loads(payload)['values'])
    archive.dependency_cache.clear()
    archive.compatibility_changes.append({'policy':'finite_owned_dnt_operations_r6','required_runtime_profile':'NN-DNT-R6',
        'runtime_validated':False,'resources':changes,'optional_location_tags':13,
        'minion_counter':'entity-local persistent tags, cap 7; no global scoreboard writes',
        'fireball_conversion':'newly created entity only; original retired only after accepted spawn'})
