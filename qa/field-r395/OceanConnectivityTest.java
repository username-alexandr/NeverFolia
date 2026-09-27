import java.util.Arrays;
import java.util.BitSet;
import net.minecraft.world.level.chunk.OceanConnectivityR395;

public final class OceanConnectivityTest {
    static int count;
    static class Grid {
        int w,d,h;byte[] a;boolean[] sky;BitSet blocked=new BitSet();
        Grid(int w,int d,int h){this.w=w;this.d=d;this.h=h;a=new byte[w*d*h];Arrays.fill(a,OceanConnectivityR395.SOLID);sky=new boolean[w*d];}
        int at(int x,int y,int z){return y*w*d+z*w+x;}
        Grid set(int x,int y,int z,byte value){a[at(x,y,z)]=value;return this;}
        Grid air(int x,int y,int z){return set(x,y,z,OceanConnectivityR395.AIR);}
        Grid water(int x,int y,int z){return set(x,y,z,OceanConnectivityR395.WATER);}
        Grid sea(int x,int z){sky[z*w+x]=true;for(int y=0;y<h;y++)water(x,y,z);return this;}
        OceanConnectivityR395.Proof solve(){return OceanConnectivityR395.solve(w,d,h,a,sky,blocked);}
    }
    static void check(boolean ok){if(!ok)throw new AssertionError();}
    static void test(String name,Runnable run){run.run();count++;System.out.println("PASS "+name);}
    public static void main(String[] args) {
        test("open vertical gap",()->{Grid g=new Grid(3,3,8).sea(1,1);g.air(1,2,1);check(g.solve().connected().get(g.at(1,2,1)));});
        test("under island roof with real side connection",()->{Grid g=new Grid(5,3,8).sea(0,1);for(int x=1;x<5;x++)g.air(x,2,1);check(g.solve().connected().get(g.at(4,2,1)));});
        test("closed roofed cave stays unproven",()->{Grid g=new Grid(5,3,8).sea(0,1);g.air(3,2,1);check(!g.solve().connected().get(g.at(3,2,1)));});
        test("underground native water is not ocean seed",()->{Grid g=new Grid(3,3,8).water(1,2,1).air(1,3,1);check(g.solve().visited()==0);});
        test("roofed top-plane water is not a seed",()->{Grid g=new Grid(3,3,8).water(1,7,1).air(1,6,1);check(g.solve().visited()==0);});
        test("diagonal water does not prove a path",()->{Grid g=new Grid(3,3,4).sea(0,0).air(1,1,1);check(!g.solve().connected().get(g.at(1,1,1)));});
        test("protected mine interrupts passage",()->{Grid g=new Grid(5,3,4).sea(0,1);for(int x=1;x<5;x++)g.air(x,1,1);g.set(2,1,1,OceanConnectivityR395.PROTECTED);check(!g.solve().connected().get(g.at(4,1,1)));});
        test("lava adjacency blocks new water",()->{Grid g=new Grid(5,3,4).sea(0,1);for(int x=1;x<5;x++)g.air(x,1,1);g.set(2,1,0,OceanConnectivityR395.LAVA);check(!g.solve().connected().get(g.at(2,1,1)));});
        test("halo lava barrier",()->{Grid g=new Grid(3,3,4).sea(1,1);g.blocked.set(g.at(1,3,1));check(g.solve().visited()==0);});
        test("unknown neighbour is not passable",()->{Grid g=new Grid(5,3,4).sea(0,1);for(int x=1;x<5;x++)g.air(x,1,1);g.set(2,1,1,OceanConnectivityR395.UNKNOWN);check(!g.solve().connected().get(g.at(4,1,1)));});
        test("crosses actual 16-block chunk boundary",()->{Grid g=new Grid(48,3,8).sea(47,1);for(int x=8;x<47;x++)g.air(x,2,1);check(g.solve().connected().get(g.at(15,2,1)));});
        test("no row wrapping",()->{Grid g=new Grid(4,3,4).sea(3,0).air(0,2,1);check(!g.solve().connected().get(g.at(0,2,1)));});
        test("no layer wrapping",()->{Grid g=new Grid(4,3,4).sea(3,2).air(0,1,0);check(!g.solve().connected().get(g.at(0,1,0)));});
        test("removed solid no longer casts heightmap shadow",()->{Grid g=new Grid(3,3,8).sea(1,1);g.set(1,4,1,OceanConnectivityR395.SOLID);check(!g.solve().connected().get(g.at(1,2,1)));g.air(1,4,1);check(g.solve().connected().get(g.at(1,2,1)));});
        test("does not cross solid ice or solid structure",()->{Grid g=new Grid(3,3,8).sea(1,1);g.set(1,4,1,OceanConnectivityR395.SOLID);check(!g.solve().connected().get(g.at(1,2,1)));});
        test("air on unknown outer boundary is not ocean seed",()->{Grid g=new Grid(3,3,8).air(0,2,1);check(g.solve().visited()==0&&g.solve().unprovenAir()==1);});
        test("immutable inputs and repeatability",()->{Grid g=new Grid(3,3,8).sea(1,1).air(2,2,1);byte[] before=g.a.clone();boolean[] sky=g.sky.clone();BitSet extra=(BitSet)g.blocked.clone();var a=g.solve();var b=g.solve();check(Arrays.equals(before,g.a)&&Arrays.equals(sky,g.sky)&&extra.equals(g.blocked)&&a.equals(b));});
        test("all-air positive volume",()->{Grid g=new Grid(8,8,640);Arrays.fill(g.a,OceanConnectivityR395.AIR);g.sky[0]=true;check(g.solve().visited()==8*8*640);});
        test("reject inconsistent shape",()->{try{OceanConnectivityR395.solve(4,4,4,new byte[3],new boolean[16],new BitSet());throw new AssertionError();}catch(IllegalArgumentException expected){}});
        test("reject unknown block code",()->{Grid g=new Grid(1,1,1);g.a[0]=9;try{g.solve();throw new AssertionError();}catch(IllegalArgumentException expected){}});
        System.out.println("R395_SOLVER_TESTS_PASSED="+count);
    }
}
