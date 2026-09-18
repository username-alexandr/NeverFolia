package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;

public final class DesertR1Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    public static void main(String[] args){
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        long seed=-2996952393010080672L;
        int activeCells=0;
        for(int cellX=-20;cellX<=20;cellX++){
            for(int cellZ=-20;cellZ<=20;cellZ++){
                int selected=0;
                for(int dx=0;dx<NeverOverworldDesertR1.CELL_CHUNKS;dx++)
                    for(int dz=0;dz<NeverOverworldDesertR1.CELL_CHUNKS;dz++)
                        if(NeverOverworldDesertR1.selectedChunk(seed,cellX*8+dx,cellZ*8+dz))selected++;
                check(selected==0||selected==1,"more than one oasis candidate in cell");
                if(selected==1)activeCells++;
            }
        }
        check(activeCells>430&&activeCells<690,"active cell ratio out of expected rare range: "+activeCells);
        for(int x=-64;x<=64;x+=7)for(int z=-64;z<=64;z+=9)
            check(NeverOverworldDesertR1.selectedChunk(seed,x,z)==NeverOverworldDesertR1.selectedChunk(seed,x,z),"determinism");
        System.out.println("PASS DesertR1Smoke checks="+checks+" activeCells="+activeCells);
    }
}
