#!/usr/bin/env python3
"""Materialize reviewed, exact-source test adapters in an isolated CI checkout."""
from pathlib import Path
import ast, hashlib, difflib
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/r3914-adapters';OUT.mkdir(parents=True,exist_ok=False)

def patch(path,blob,replacements):
    p=ROOT/path;raw=p.read_bytes()
    actual=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
    if actual!=blob:raise ValueError('Unreviewed source: '+path)
    before=raw.decode();text=before
    for old,new in replacements:
        if text.count(old)!=1:raise ValueError('Ambiguous transformation: '+path+' '+old[:60])
        text=text.replace(old,new,1)
    if p.suffix=='.py':ast.parse(text,filename=path)
    (OUT/(p.name+'.before')).write_bytes(raw)
    (OUT/(p.name+'.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True),text.splitlines(True),fromfile='a/'+path,tofile='b/'+path)))
    p.write_text(text)

patch('qa/field-r3913/build.py','aa6dc8f857e91841511a1d460d5127dd72528ccb',[
    ('NeverOverworldIceFragmentsR3913.apply(task.world, task.fromChunk); // R3913_ICE_FRAGMENTS','NeverOverworldIceFragmentsR3913.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R3914_PIECE_AWARE_ICE'),
    ("'version':'R39.13-ICE-TEST'","'version':'R39.14-INTEGRATION-WORK'"),
])
patch('qa/field-r3913/R3913IceQa.java','91b1e780fa9d2280495278ab10e4be06b4c8e0e4',[
    ('"frosted_ice_retained","bottom_boundary_retained"};','"frosted_ice_retained","bottom_boundary_retained","distant_persisted_mine_does_not_disable_chunk","mine_envelope_neighbour_retained"};'),
    ('            case 18 -> {put(c,8,64,8,Blocks.WATER.defaultBlockState());put(c,8,-511,8,Blocks.ICE.defaultBlockState());expected=0;}','            case 18 -> {put(c,8,64,8,Blocks.WATER.defaultBlockState());put(c,8,-511,8,Blocks.ICE.defaultBlockState());expected=0;}\n            case 19 -> c.persistentDataContainer.set(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY,new int[]{1,1,1,20,1,3,22,3});\n            case 20 -> {c.persistentDataContainer.set(new NamespacedKey("neverfolia","dry_mines_r12"),PersistentDataType.INTEGER_ARRAY,new int[]{1,1,10,64,8,12,66,10});expected=0;}'),
])
patch('qa/field-r3913/runtime.py','72b1404e598cea7082ba5158f9246275c91a5f45',[
    ("len(observed['rows'])==19","len(observed['rows'])==21"),
    ("        report['pass']=all(p['pass'] for p in report['phases'].values()) and all(p['pass'] for p in report['comparisons'].values())","        report['natural_effect_observed']=report['comparisons']['off_vs_candidate']['changed']>0\n        report['pass']=all(p['pass'] for p in report['phases'].values()) and all(p['pass'] for p in report['comparisons'].values()) and report['natural_effect_observed']"),
])
print('R3914 exact-source adapters prepared; no game process executed by this script.')
