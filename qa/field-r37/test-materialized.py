#!/usr/bin/env python3
"""Execute actual materialized R37 Java method bodies with minimal block storage.

This is a unit regression, NOT a substitute for a live Java25/Folia seed test.
No Minecraft generation algorithm is reimplemented in the assertions.
"""
import argparse, importlib.util, json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('r37',ROOT/'scripts/apply-never-overworld-r37.py')
r37=importlib.util.module_from_spec(spec);spec.loader.exec_module(r37)

def method(text, signature):
 a,b=r37.method_bounds(text,signature)
 return text[a:b].replace('net.minecraft.world.level.levelgen.Heightmap.Types','Heightmap.Types')

STUBS=r'''
import java.util.*;
public class R37Regression {
 static int checks;
 static final int FLOOD_LEVEL=128, SCAN_MAX_Y=128;
 static final int CACHE_CHUNK_WIDTH=3, CACHE_BLOCK_WIDTH=48;
 static final class BlockState {
  final String name; BlockState(String n){name=n;}
  boolean is(BlockState other){return name.equals(other.name);}
  FluidState getFluidState(){return new FluidState(name.startsWith("water")||name.equals("lava"));}
 }
 record FluidState(boolean wet){boolean isEmpty(){return !wet;}}
 static final class Blocks {static final BlockState WATER=new BlockState("water"), AIR=new BlockState("air"), STONE=new BlockState("stone"), LAVA=new BlockState("lava");}
 static class BlockPos {
  int x,y,z; BlockPos(int x,int y,int z){this.x=x;this.y=y;this.z=z;}
  int getX(){return x;}int getY(){return y;}int getZ(){return z;}
  static class MutableBlockPos extends BlockPos {MutableBlockPos(){super(0,0,0);}void set(int x,int y,int z){this.x=x;this.y=y;this.z=z;}}
 }
 record ChunkPos(int x,int z){int getMinBlockX(){return x*16;}int getMinBlockZ(){return z*16;}}
 static final class Heightmap {enum Types{OCEAN_FLOOR_WG}}
 static final class ChunkAccess {
  final ChunkPos cp; final int[] floor=new int[256]; final Map<String,BlockState> states=new HashMap<>(); final Set<String> protectedCells=new HashSet<>(); int writes;
  ChunkAccess(int x,int z,int f){cp=new ChunkPos(x,z);Arrays.fill(floor,f);}
  ChunkPos getPos(){return cp;}int getMinY(){return -512;}int getMaxY(){return 512;}
  String key(BlockPos p){if(p.x>>4!=cp.x||p.z>>4!=cp.z)throw new AssertionError("foreign chunk access "+p.x+","+p.z);return p.x+":"+p.y+":"+p.z;}
  int getHeight(Heightmap.Types type,int x,int z){return floor[(z&15)*16+(x&15)];}
  BlockState getBlockState(BlockPos p){return states.getOrDefault(key(p),Blocks.AIR);}
  void setBlockState(BlockPos p,BlockState s,int flags){states.put(key(p),s);writes++;}
  void put(int x,int y,int z,BlockState s){states.put(key(new BlockPos(x,y,z)),s);}
 }
 static final class NeverOverworldDryMinesR12 {static boolean protectedCell(ChunkAccess c,BlockPos p){return c.protectedCells.contains(c.key(p));}}
 static boolean isFloodableAt(ChunkAccess c,BlockPos p){return c.getBlockState(p).is(Blocks.AIR)||c.getBlockState(p).name.startsWith("water");}
 static boolean traversable(ChunkAccess c,BlockPos p){return isFloodableAt(c,p)&&!NeverOverworldDryMinesR12.protectedCell(c,p);}
 static boolean lavaAtCache(ChunkAccess[] c,int x,int y,int z,BlockPos.MutableBlockPos p){return false;}
 static void check(boolean condition,String label){if(!condition)throw new AssertionError(label);checks++;}
'''
MAIN=r'''
 public static void main(String[] args){
  for(int cx:new int[]{-4,-1,0,3}){
   ChunkAccess c=new ChunkAccess(cx,3,63);int bx=c.getPos().getMinBlockX(),bz=c.getPos().getMinBlockZ();
   c.floor[0]=160; // dry cave under a mountain, including a native flowing cell
   BlockState nativeFlow=new BlockState("water_level_5");c.put(bx,52,bz,nativeFlow);
   c.put(bx+1,75,bz,nativeFlow); // open ocean flow must also remain verbatim
   c.floor[2]=96; // occupied block Y96 => first synthetic WATER at Y97
   c.put(bx+2,96,bz,Blocks.STONE);
   c.protectedCells.add(c.key(new BlockPos(bx+3,90,bz)));
   floodSurfaceConnectedVolume(c,-511,128,Blocks.WATER);
   check(c.getBlockState(new BlockPos(bx,110,bz)).is(Blocks.AIR),"roofed cave stays air");
   check(c.getBlockState(new BlockPos(bx,52,bz))==nativeFlow,"native cave water exact state");
   check(c.getBlockState(new BlockPos(bx+1,75,bz))==nativeFlow,"native open-column flow exact state");
   for(int y=64;y<=128;y++)if(y!=75)check(c.getBlockState(new BlockPos(bx+1,y,bz)).is(Blocks.WATER),"no Y64..95 ocean air slab");
   check(c.getBlockState(new BlockPos(bx+2,96,bz)).is(Blocks.STONE),"ocean-floor stone preserved");
   check(c.getBlockState(new BlockPos(bx+2,97,bz)).is(Blocks.WATER),"first cell above floor filled");
   check(c.getBlockState(new BlockPos(bx+3,90,bz)).is(Blocks.AIR),"protected mine mask retained");
   int writes=c.writes;floodSurfaceConnectedVolume(c,-511,128,Blocks.WATER);check(c.writes==writes,"repeat pass performs no water rewrites");
   ChunkAccess[] cache=new ChunkAccess[9];cache[4]=c;
   var pos=new BlockPos.MutableBlockPos();var adjacent=new BlockPos.MutableBlockPos();
   check(!traversableCache(cache,16,110,16,pos,adjacent),"cache rejects roofed air");
   // Native water is readable evidence, never authorization to write roofed air.
   c.put(bx,110,bz,Blocks.WATER);
   check(traversableCache(cache,16,110,16,pos,adjacent),"cache preserves native water");
   check(!traversableCache(cache,0,110,0,pos,adjacent),"missing neighbour remains missing");
   check(!traversableCache(cache,-1,110,16,pos,adjacent),"negative cache index rejected");
  }
  System.out.println("R37 materialized Java unit checks passed: "+checks);
 }
}
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 owner=(a.folia/r37.OWNER).read_text();cache=(a.folia/r37.CACHE).read_text();template=(a.folia/r37.TEMPLATE).read_text()
 r37.verify(owner,cache,template)
 assert r37.patch_owner(owner)==owner and r37.patch_cache(cache)==cache and r37.patch_template(template)==template
 # Negative control: reject reintroduction of precisely the missing write gate.
 try:r37.verify(owner,cache.replace(r37.CACHE_WRITE_NEW,r37.CACHE_WRITE_OLD),template)
 except ValueError:pass
 else:raise AssertionError('unguarded cache write was accepted')
 code=STUBS+'\n'+method(owner,'    private static void floodSurfaceConnectedVolume(')+'\n'+method(owner,'    private static boolean customOceanColumnOpen(')+'\n'+method(cache,'    private static boolean traversableCache(')+'\n'+MAIN
 with tempfile.TemporaryDirectory(prefix='neverfolia-r37-') as td:
  path=Path(td)/'R37Regression.java';path.write_text(code)
  subprocess.run(['javac','-d',td,str(path)],check=True)
  result=subprocess.run(['java','-ea','-cp',td,'R37Regression'],check=True,capture_output=True,text=True)
 print(result.stdout.strip())
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'pass':True,'scope':'actual-method unit regression with minimal storage; not live world QA','result':result.stdout.strip(),'idempotent':True,'negative_cache_write_control':True},indent=2)+'\n')
if __name__=='__main__':main()
