package net.minecraft.server.level;

public final class SandstormR1Smoke {
    private static int checks;
    private static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);checks++;}
    public static void main(String[] args){
        long seed=-2996952393010080672L;
        check(!NeverOverworldSandstormR1.isDryDesertSurface(128),"flooded desert sea must not run sandstorms");
        check(NeverOverworldSandstormR1.isDryDesertSurface(129),"dry flood-boundary desert must allow sandstorms");
        check(NeverOverworldSandstormR1.isDryDesertSurface(180),"high dry desert must allow sandstorms");
        double against=NeverOverworldSandstormR1.windImpulse(-0.10D,0.0D,1.0D,0.0D);
        double neutral=NeverOverworldSandstormR1.windImpulse(0.0D,0.10D,1.0D,0.0D);
        double with=NeverOverworldSandstormR1.windImpulse(0.10D,0.0D,1.0D,0.0D);
        check(Math.abs(against-0.0060D)<1.0e-12,"against-wind impulse "+against);
        check(Math.abs(neutral-0.0044D)<1.0e-12,"cross-wind impulse "+neutral);
        check(Math.abs(with-0.0032D)<1.0e-12,"with-wind impulse "+with);
        check(against>neutral&&neutral>with,"wind response ordering");
        int enabledCycles=0;
        for(long cycle=-100;cycle<100;cycle++){
            long base=cycle*NeverOverworldSandstormR1.CYCLE_TICKS;
            boolean any=false;
            double wx=0,wz=0;
            for(long t=0;t<NeverOverworldSandstormR1.CYCLE_TICKS;t+=100){
                var s=NeverOverworldSandstormR1.storm(seed,base+t);
                double len=Math.sqrt(s.windX()*s.windX()+s.windZ()*s.windZ());
                check(Math.abs(len-1.0)<1.0e-9,"wind not normalized");
                if(t==0){wx=s.windX();wz=s.windZ();}
                else check(Math.abs(wx-s.windX())<1e-12&&Math.abs(wz-s.windZ())<1e-12,"wind changed within cycle");
                any|=s.active();
            }
            if(any)enabledCycles++;
        }
        check(enabledCycles>50&&enabledCycles<90,"storm frequency out of bounds "+enabledCycles);
        var a=NeverOverworldSandstormR1.storm(seed,123456L);
        var b=NeverOverworldSandstormR1.storm(seed,123456L);
        check(a.equals(b),"storm state non-deterministic");
        System.out.println("PASS SandstormR1Smoke checks="+checks+" stormCycles="+enabledCycles);
    }
}
