from pathlib import Path
import sys,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).parent));import carts
nbt=carts.load(ROOT/'scripts/build-never-overworld-external-structures-r19.py','r41inspectnbt')
with zipfile.ZipFile('core/NeverOverworld.zip') as z:
 for biome in carts.BIOMES:
  n=carts.PREFIX+'armorer_'+biome+'.nbt';root=nbt._nbt_parse(z.read(n))[2];m=carts.model(root)
  j={str(p):r for p,r in m['blocks'].items() if r.get('nbt',(10,{}))[1].get('id')==(8,'minecraft:jigsaw')}
  print('CART_EXACT',json.dumps({'biome':biome,'size':root['size'],'count':len(m['blocks']),'jigsaw':j,'root_keys':list(root)}))
  if biome=='pale':print('PALE_MODEL',json.dumps({str(p):r for p,r in m['blocks'].items()}))
 for n in z.namelist():
  if n.endswith('.mcfunction'):print('ACTUAL_FUNCTION',n,z.read(n).decode())
  if '/loot_table/' in n and any(t in n for t in ('shrine_weapons','spiderqueen','toxic_lair/boss/slime','spawners/nether_port','spawner_projectile/nether_')):print('ACTUAL_LOOT',n,z.read(n).decode())
