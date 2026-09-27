#!/usr/bin/env python3
"""Inspect typed NBT differences; no repairs yet."""
from pathlib import Path
import argparse,copy,json,zipfile
from inspect_sources import module,ROOT,plain,summary

def diff(a,b,path=''):
    if type(a) is not type(b):return [(path,a,b)]
    if isinstance(a,dict):
        rows=[]
        for k in sorted(set(a)|set(b)):
            if k not in a or k not in b:rows.append((path+'/'+k,a.get(k),b.get(k)))
            else:rows.extend(diff(a[k],b[k],path+'/'+k))
        return rows
    if isinstance(a,(tuple,list)):
        if len(a)!=len(b):return [(path+'/length',len(a),len(b))]
        return [r for i,(x,y) in enumerate(zip(a,b)) for r in diff(x,y,path+'/'+str(i))]
    return [] if a==b else [(path,a,b)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,required=True);p.add_argument('--debug',type=Path,required=True);a=p.parse_args()
    builder=module('r394cart',ROOT/'scripts/build-never-overworld-external-structures-r19.py')
    prefix='data/nova_structures/structure/tavern/tavern_event_trader_car_'
    with zipfile.ZipFile(a.pack) as z:
        for suffix in ('armorer','armorer_acacia','armorer_oak','butcher_acacia','farmer_acacia','cleric','cartographer'):
            name=prefix+suffix+'.nbt';_,_,root=builder._nbt_parse(z.read(name))
            print('CART',suffix,json.dumps(plain((10,root))),flush=True)
        for biome in ('acacia','birch','cherry','desert','jungle','mangrove','oak','pale','snowy','spruce','swamp'):
            base=plain((10,builder._nbt_parse(z.read(prefix+'armorer_'+biome+'.nbt'))[2]))
            for role in ('butcher','farmer','fisher','fletcher','grindstone','leather_worker','librarian','loom','smithing_table','stonecutter'):
                other=plain((10,builder._nbt_parse(z.read(prefix+role+'_'+biome+'.nbt'))[2]))
                rows=diff(base,other)
                print('WRAPPER_DIFF',biome,role,json.dumps(rows),flush=True)
        for path in z.namelist():
            if '/worldgen/template_pool/' in path and path.endswith('.json') and ('trader' in path or 'tavern' in path and path!='data/nova_structures/worldgen/template_pool/tavern.json'):
                obj=json.loads(z.read(path))
                if any(s in str(obj) for s in ('cleric','cartographer','trader_car')):print('CART_POOL',path,json.dumps(obj),flush=True)
    with zipfile.ZipFile(a.debug/'diagnostics.zip') as z:
        for suffix,needles in [('StructureTemplate.java',('placeInWorld','getSize','getPalettes','filterBlocks')),('PlaceCommand.java',('placeInWorld','getStructure','StructurePlaceSettings','setRotation','RandomSource')),('StructureTemplateManager.java',('public Optional','public Structure','getOrCreate')),('Commands.java',('PlaceCommand.register','DataPackCommand.register'))]:
            paths=[n for n in z.namelist() if n.endswith('/'+suffix)];assert len(paths)==1,paths
            lines=z.read(paths[0]).decode().splitlines()
            for i,line in enumerate(lines):
                if any(v in line for v in needles):print('API',suffix,i+1,'\n'.join(lines[max(0,i-1):i+12]),flush=True)
if __name__=='__main__':main()
