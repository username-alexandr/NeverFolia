import java.util.Arrays;
import net.minecraft.world.level.chunk.OceanConnectivityR3926;

public final class OceanConnectivityR3926Test {
    static int count;
    static class Grid {
        int w,d,h;byte[] a;
        Grid(int w,int d,int h){this.w=w;this.d=d;this.h=h;a=new byte[w*d*h];Arrays.fill(a,OceanConnectivityR3926.SOLID);}
        int at(int x,int y,int z){return y*w*d+z*w+x;}
        Grid set(int x,int y,int z,byte v){a[at(x,y,z)]=v;return this;}
        Grid air(int x,int y,int z){return set(x,y,z,OceanConnectivityR3926.AIR);}
        Grid water(int x,int y,int z){return set(x,y,z,OceanConnectivityR3926.WATER);}
        OceanConnectivityR3926.Proof solve(){return OceanConnectivityR3926.solve(w,d,h,a);}
    }
    static void ok(boolean v){if(!v)throw new AssertionError();}
    static void test(String n,Runnable r){r.run();count++;System.out.println("PASS "+n);}

    public static void main(String[] args) {
        test("top-plane air is ocean seed",()->{
            Grid g=new Grid(3,3,6);for(int y=1;y<6;y++)g.air(1,y,1);
            ok(g.solve().connected().get(g.at(1,1,1)));
        });
        test("closed cave stays dry",()->{
            Grid g=new Grid(3,3,6).air(1,1,1);
            ok(!g.solve().connected().get(g.at(1,1,1)));
        });
        test("side tunnel reaches sea plane",()->{
            Grid g=new Grid(7,3,6);
            for(int x=1;x<7;x++)g.air(x,1,1);
            for(int y=1;y<6;y++)g.air(6,y,1);
            ok(g.solve().connected().get(g.at(1,1,1)));
        });
        test("protected cell closes cave mouth",()->{
            Grid g=new Grid(5,3,6);
            for(int x=1;x<5;x++)g.air(x,1,1);
            for(int y=1;y<6;y++)g.air(4,y,1);
            g.set(2,1,1,OceanConnectivityR3926.PROTECTED);
            ok(!g.solve().connected().get(g.at(1,1,1)));
        });
        test("lava halo blocks new water path",()->{
            Grid g=new Grid(5,3,6);
            for(int x=1;x<5;x++)g.air(x,1,1);
            for(int y=1;y<6;y++)g.air(4,y,1);
            g.set(2,1,0,OceanConnectivityR3926.LAVA);
            ok(!g.solve().connected().get(g.at(1,1,1)));
        });
        test("unknown is never exterior",()->{
            Grid g=new Grid(3,3,6).air(1,1,1);
            g.set(1,5,1,OceanConnectivityR3926.UNKNOWN);
            ok(!g.solve().connected().get(g.at(1,1,1)));
        });
        test("top-plane water seeds connected air",()->{
            Grid g=new Grid(3,3,6).water(1,5,1).air(1,4,1).air(1,3,1);
            ok(g.solve().connected().get(g.at(1,3,1)));
        });
        test("solid top plane keeps enclosed component dry",()->{
            Grid g=new Grid(3,3,6).air(1,1,1).air(1,2,1).air(1,3,1).air(1,4,1);
            ok(!g.solve().connected().get(g.at(1,1,1)));
        });
        test("immutable and repeatable",()->{
            Grid g=new Grid(3,3,6);for(int y=1;y<6;y++)g.air(1,y,1);
            byte[] before=g.a.clone();var a=g.solve();var b=g.solve();
            ok(Arrays.equals(before,g.a)&&a.equals(b));
        });
        test("reject malformed volume",()->{
            try{OceanConnectivityR3926.solve(2,2,2,new byte[2]);throw new AssertionError();}
            catch(IllegalArgumentException expected){}
        });
        System.out.println("R3926_SOLVER_TESTS_PASSED="+count);
    }
}
