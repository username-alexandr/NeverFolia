package net.minecraft.world.level.chunk;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;

public final class DesertR1Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    public static void main(String[] args){
        SharedConstants.tryDetectVersion();Bootstrap.bootStrap();
        long seed=-2996952393010080672L;
        int selected=0;
        int total=0;
        for(int x=-384;x<=384;x++){
            for(int z=-384;z<=384;z++){
                boolean a=NeverOverworldDesertR1.selectedChunk(seed,x,z);
                boolean b=NeverOverworldDesertR1.selectedChunk(seed,x,z);
                check(a==b,"selection non-deterministic");
                if(a)selected++;
                total++;
            }
        }
        double rate=(double)selected/(double)total;
        double expected=1.0D/NeverOverworldDesertR1.OASIS_CHANCE_DENOMINATOR;
        check(rate>expected*0.75D&&rate<expected*1.25D,
            "oasis candidate rate out of bounds selected="+selected+" total="+total+" rate="+rate);
        check(!NeverOverworldDesertR1.selectedChunk(seed,0,0)
              || NeverOverworldDesertR1.selectedChunk(seed,0,0),"repeat determinism");
        System.out.println("PASS DesertR1Smoke checks="+checks+" selected="+selected+" rate="+rate);
    }
}
