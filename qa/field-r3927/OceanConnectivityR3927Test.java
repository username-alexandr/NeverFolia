import java.util.Arrays;
import net.minecraft.world.level.chunk.OceanConnectivityR3927;

public final class OceanConnectivityR3927Test {
    static int count;
    static class Grid {
        final int w,d,h;final byte[] a;
        Grid(int w,int d,int h){this.w=w;this.d=d;this.h=h;a=new byte[w*d*h];Arrays.fill(a,OceanConnectivityR3927.SOLID);}
        int at(int x,int y,int z){return y*w*d+z*w+x;}
        Grid set(int x,int y,int z,byte v){a[at(x,y,z)]=v;return this;}
        Grid air(int x,int y,int z){return set(x,y,z,OceanConnectivityR3927.AIR);}
        Grid carved(int x,int y,int z){return set(x,y,z,OceanConnectivityR3927.CARVED_AIR);}
        Grid water(int x,int y,int z){return set(x,y,z,OceanConnectivityR3927.WATER);}
        OceanConnectivityR3927.Proof solve(int sea){return OceanConnectivityR3927.solve(w,d,h,a,sea);}
    }
    static void ok(boolean v){if(!v)throw new AssertionError();}
    static void test(String n,Runnable r){r.run();count++;System.out.println("PASS "+n);}

    public static void main(String[] args) {
        test("top plane still seeds raised ocean",()->{
            Grid g=new Grid(5,5,8);
            for(int y=2;y<8;y++)g.air(2,y,2);
            ok(g.solve(1).connected().get(g.at(2,2,2)));
        });
        test("closed carved cave stays dry",()->{
            Grid g=new Grid(5,5,8).carved(2,2,2).carved(2,3,2);
            var p=g.solve(1);ok(!p.connected().get(g.at(2,2,2))&&p.carvedAir()==2);
        });
        test("ocean connected carved cave floods",()->{
            Grid g=new Grid(5,5,8);
            for(int y=2;y<8;y++)g.air(2,y,2);
            g.carved(2,2,2);
            var p=g.solve(1);ok(p.connected().get(g.at(2,2,2))&&p.connectedCarvedAir()==1);
        });
        test("broad native sea sheet seeds under roof",()->{
            Grid g=new Grid(8,8,8);
            for(int z=0;z<8;z++)for(int x=0;x<8;x++)g.water(x,2,z);
            for(int y=3;y<=5;y++)g.air(4,y,4);
            // top plane remains solid: only the native sea sheet can prove ocean.
            var p=g.solve(2);
            ok(p.nativeSeaSeedCells()>=8&&p.connected().get(g.at(4,5,4)));
        });
        test("small aquifer is not ocean seed",()->{
            Grid g=new Grid(8,8,8);
            g.water(3,2,3).water(4,2,3).water(3,2,4).water(4,2,4).air(3,3,3);
            var p=g.solve(2);
            ok(p.nativeSeaComponents()==0&&!p.connected().get(g.at(3,3,3)));
        });
        test("two edge native sheet accepted",()->{
            Grid g=new Grid(8,8,8);
            for(int x=0;x<8;x++)g.water(x,2,0);
            for(int z=0;z<8;z++)g.water(0,2,z);
            g.air(1,3,0);
            var p=g.solve(2);ok(p.nativeSeaComponents()>=1&&p.connected().get(g.at(1,3,0)));
        });
        test("protected cell blocks ocean",()->{
            Grid g=new Grid(5,5,8);
            for(int y=2;y<8;y++)g.air(2,y,2);
            g.set(2,4,2,OceanConnectivityR3927.PROTECTED);
            ok(!g.solve(1).connected().get(g.at(2,2,2)));
        });
        test("lava halo blocks path",()->{
            Grid g=new Grid(5,5,8);
            for(int y=2;y<8;y++)g.air(2,y,2);
            g.set(1,4,2,OceanConnectivityR3927.LAVA);
            ok(!g.solve(1).connected().get(g.at(2,4,2)));
        });
        test("unknown neighbour is not passable",()->{
            Grid g=new Grid(5,5,8);
            for(int y=2;y<8;y++)g.air(2,y,2);
            g.set(2,4,2,OceanConnectivityR3927.UNKNOWN);
            ok(!g.solve(1).connected().get(g.at(2,2,2)));
        });
        test("immutable and repeatable",()->{
            Grid g=new Grid(5,5,8);for(int y=2;y<8;y++)g.air(2,y,2);
            byte[] before=g.a.clone();var a=g.solve(1);var b=g.solve(1);
            ok(Arrays.equals(before,g.a)&&a.equals(b));
        });
        test("reject malformed",()->{
            try{OceanConnectivityR3927.solve(2,2,2,new byte[3],1);throw new AssertionError();}
            catch(IllegalArgumentException expected){}
        });
        System.out.println("R3927_SOLVER_TESTS_PASSED="+count);
    }
}
