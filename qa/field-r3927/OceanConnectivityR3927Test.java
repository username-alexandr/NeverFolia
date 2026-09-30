import java.util.Arrays;
import net.minecraft.world.level.chunk.OceanConnectivityR3927;
public final class OceanConnectivityR3927Test {
 static int n;
 static class G{int w,d,h;byte[] a;G(int w,int d,int h){this.w=w;this.d=d;this.h=h;a=new byte[w*d*h];Arrays.fill(a,OceanConnectivityR3927.SOLID);}int i(int x,int y,int z){return y*w*d+z*w+x;}G s(int x,int y,int z,byte v){a[i(x,y,z)]=v;return this;}G air(int x,int y,int z){return s(x,y,z,OceanConnectivityR3927.AIR);}G cave(int x,int y,int z){return s(x,y,z,OceanConnectivityR3927.CAVE);}OceanConnectivityR3927.Proof solve(){return OceanConnectivityR3927.solve(w,d,h,a);}}
 static void ok(boolean v){if(!v)throw new AssertionError();}static void t(String s,Runnable r){r.run();n++;System.out.println("PASS "+s);}
 public static void main(String[]x){
  t("sea connected cave floods",()->{G g=new G(3,3,8);for(int y=2;y<8;y++)g.cave(1,y,1);ok(g.solve().flood().get(g.i(1,2,1)));});
  t("sealed carved cave stays dry",()->{G g=new G(8,8,64);for(int x1=2;x1<6;x1++)for(int z=2;z<6;z++)for(int y=20;y<24;y++)g.cave(x1,y,z);ok(g.solve().flood().isEmpty());});
  t("large shallow unproven air inferred ocean",()->{G g=new G(8,8,64);for(int x1=1;x1<7;x1++)for(int z=1;z<7;z++)for(int y=40;y<42;y++)g.air(x1,y,z);ok(g.solve().inferredOcean()==72);});
  t("one cave provenance protects whole component",()->{G g=new G(8,8,64);for(int x1=1;x1<7;x1++)for(int z=1;z<7;z++)for(int y=40;y<42;y++)g.air(x1,y,z);g.cave(1,40,1);ok(g.solve().inferredOcean()==0&&g.solve().dryCave()==72);});
  t("deep unproven air conservative dry",()->{G g=new G(8,8,128);for(int x1=1;x1<7;x1++)for(int z=1;z<7;z++)for(int y=20;y<22;y++)g.air(x1,y,z);ok(g.solve().inferredOcean()==0&&g.solve().unresolvedAir()==72);});
  t("small shallow pocket conservative dry",()->{G g=new G(8,8,64);for(int x1=1;x1<3;x1++)for(int z=1;z<3;z++)for(int y=50;y<52;y++)g.air(x1,y,z);ok(g.solve().inferredOcean()==0);});
  System.out.println("R3927_SOLVER_TESTS_PASSED="+n);
 }
}
