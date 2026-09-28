#!/usr/bin/env python3
from pathlib import Path
import hashlib,importlib.util,os,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';OUT.mkdir(exist_ok=True)
WORK=ROOT/'.work/r3915';WORK.mkdir(parents=True,exist_ok=True)
CORE='9571073a77086b04ce54594fe2b91737fdf9daf4019d4ce585016f77c03912f6'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def main():
    jars=list((ROOT/'inputs').rglob('server.jar'));need(len(jars)==1,'Ambiguous server')
    need(hashlib.sha256(jars[0].read_bytes()).hexdigest()==CORE,'Wrong server')
    libs=WORK/'libs';libs.mkdir(exist_ok=False)
    with zipfile.ZipFile(jars[0]) as z:
        for i,n in enumerate(z.namelist()):
            if n.endswith('.jar') and n.startswith(('META-INF/versions/','META-INF/libraries/')):(libs/(str(i)+'-'+Path(n).name)).write_bytes(z.read(n))
    spec=importlib.util.spec_from_file_location('cart_runtime',ROOT/'qa/field-r3914/run_carts.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.resolve_api(libs,list((ROOT/'debug').rglob('diagnostics.zip')))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    (WORK/'classpath.txt').write_text(cp)
    names=('net.minecraft.server.level.ServerPlayer','net.minecraft.server.level.ClientInformation','net.minecraft.world.entity.player.Input','net.minecraft.world.entity.animal.happyghast.HappyGhast','net.minecraft.world.entity.Entity','net.minecraft.world.item.enchantment.Enchantment','net.minecraft.world.item.enchantment.EnchantmentEffectComponents','net.minecraft.world.entity.ai.attributes.AttributeInstance','net.minecraft.world.entity.ai.attributes.AttributeModifier')
    for name in names:
        p=subprocess.run(['javap','-p','-classpath',cp,name],text=True,capture_output=True,timeout=30)
        (OUT/(name.rsplit('.',1)[-1]+'.api.txt')).write_text(p.stdout+p.stderr)
        print('ACTUAL_API',name,'exit',p.returncode,flush=True)
        if p.returncode:print(p.stderr,flush=True);continue
        terms=('ServerPlayer(','ClientInformation(','Input(','effects(','TICK','Input','input','Controll','Passenger','startRiding','Harness','riding','Modifier','Flying','AttributeInstance(','AttributeModifier(','getValue','createDefault','enchantment')
        for line in p.stdout.splitlines():
            if any(t in line for t in terms):print(line,flush=True)
    for name in ('net.minecraft.world.entity.animal.happyghast.HappyGhast',):
        p=subprocess.run(['javap','-c','-p','-classpath',cp,name],text=True,capture_output=True,timeout=30)
        (OUT/(name.rsplit('.',1)[-1]+'.code.txt')).write_text(p.stdout+p.stderr)
        rows=p.stdout.splitlines()
        for i,line in enumerate(rows):
            if 'getControllingPassenger(' in line:print('\n'.join(rows[i:i+80]),flush=True)
if __name__=='__main__':main()
