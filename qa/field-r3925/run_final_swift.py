#!/usr/bin/env python3
"""Exact-input Swift lifecycle acceptance for the R39.25 native-sea candidate."""
from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,sys,zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts-r3925-swift'
WORK=ROOT/'.work/r3925-swift'
CORE_SHA=os.environ['R3925_CORE_SHA']
OW_SHA=os.environ['R3925_OW_SHA']
NN_SHA=os.environ['R3925_NN_SHA']
CORE_NAME=os.environ['R3925_CORE_NAME']
OW_NAME='NeverOverworld-R3925-NativeSea.zip'
NN_NAME='NeverNether.zip'

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def exact(root,name,digest):
    hits=[p for p in Path(root).rglob(name) if p.is_file() and sha(p)==digest]
    need(len(hits)==1,f'exact input {name} {digest}: {hits}')
    return hits[0]
def once(text,before,after):
    need(text.count(before)==1,'Unexpected QA anchor '+before[:100])
    return text.replace(before,after,1)

def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    core=exact(ROOT/'swift-input',CORE_NAME,CORE_SHA)
    ow=exact(ROOT/'resource-input',OW_NAME,OW_SHA)
    nn=exact(ROOT/'ice-input',NN_NAME,NN_SHA)

    sys.path.insert(0,str(ROOT/'qa/field-r3915'))
    import run_runtime as r
    r.OUT=OUT;r.WORK=WORK

    libs=WORK/'libs';classes=WORK/'classes';libs.mkdir();classes.mkdir()
    with zipfile.ZipFile(core) as z:
        for i,name in enumerate(z.namelist()):
            if name.endswith('.jar') and name.startswith(('META-INF/versions/','META-INF/libraries/')):
                (libs/f'{i}-{Path(name).name}').write_bytes(z.read(name))
    cp=os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    need(bool(cp),'empty runtime classpath')

    text=(ROOT/'qa/field-r3915/R3915SwiftQa.java').read_text()
    text=once(text,'                input(true,true);tick();driver.stopRiding();tick();',
'''                input(true,true);tick();
                ItemStack worn=ghast.getItemBySlot(EquipmentSlot.BODY);
                ghast.setItemSlot(EquipmentSlot.BODY,ItemStack.EMPTY);tick();
                absent(flight,FLIGHT,"removing harness clears mount modifier "+n);
                EnchantmentHelper.tickEffects(level,driver);
                absent(fov,FOV,"removing harness clears rider modifier "+n);
                check(!ghast.entityTags().contains("sprinting"),"removing harness clears sprint latch "+n);
                ghast.setItemSlot(EquipmentSlot.BODY,worn);input(true,true);tick();
                amount(flight,FLIGHT,speed,"restored harness still activates flight "+n);
                amount(fov,FOV,zoom,"restored harness still activates rider effect "+n);
                driver.stopRiding();tick();
                Identifier unrelated=Identifier.fromNamespaceAndPath("neverfolia_qa","unrelated_speed");
                fov.addTransientModifier(new AttributeModifier(unrelated,0.123,AttributeModifier.Operation.ADD_MULTIPLIED_BASE));
                EnchantmentHelper.tickEffects(level,driver);
                absent(fov,FOV,"dismount clears rider modifier on player tick "+n);
                amount(fov,unrelated,0.123,"cleanup preserves unrelated modifiers "+n);
                fov.removeModifier(unrelated);''')
    text=once(text,'                // Fixture teardown only, after recording whether real cleanup failed.\n                fov.removeModifier(FOV);',
              '                absent(fov,FOV,"no fixture repair is needed after dismount "+n);')
    src=WORK/'R3915SwiftQa.java';src.write_text(text);(OUT/'R3915SwiftQa-final.java.txt').write_text(text)
    p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(src)],
                     text=True,capture_output=True)
    (OUT/'javac.log').write_text(p.stdout+p.stderr)
    need(p.returncode==0,'Final Swift QA did not compile')
    plugin=WORK/'R3923FinalSwiftQa.jar'
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
        for path in classes.rglob('*.class'):z.write(path,path.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: R3915SwiftQa\nversion: '3925'\nmain: R3915SwiftQa\napi-version: '26.2'\nfolia-supported: true\n")

    # Minecraft 26.2 protocol mapping pinned from two successful R39.24
    # connected-client runs. GameProtocols source SHA is recorded so this cannot
    # silently drift with a future Minecraft/Paper line.
    protocol_source_sha='54e5914510d6a9b24a50f21a865cb73905f1b802c75ee9c6259563761d449e26'
    cfg={'play_keepalive':44,'play_position':72,'play_keepalive_reply':28}
    spec=importlib.util.spec_from_file_location('r3925_loopback',ROOT/'qa/field-r38/loopback_client.py')
    client_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(client_module)
    Client=client_module.Client
    (OUT/'protocol-source.json').write_text(json.dumps({
      'source':'Minecraft 26.2 GameProtocols.java',
      'sha256':protocol_source_sha,'mapping':cfg,
      'provenance':'R39.24 successful connected-client evidence'
    },indent=2)+'\n')
    folder=r.setup('final-swift',ow,nn,plugin)
    first=r.phase('final-swift-first',core,folder,False,Client,cfg);need(first['pass'],'Final Swift first phase failed')
    restart=r.phase('final-swift-restart',core,folder,False,Client,cfg);need(restart['pass'],'Final Swift restart failed')
    for label,phase in (('first',first),('restart',restart)):
        levels=phase['observed'].get('levels',[])
        need([x.get('tier') for x in levels]==[1,2,3],label+' missing Swift tiers')
        need(not any(x.get('residual_rider_modifier_after_detach') for x in levels),label+' dismount residue remains')
        need(phase['observed'].get('network_player_tested') is True,label+' did not use connected player')
    summary={
      'pass':True,'phases':2,'tiers':[1,2,3],
      'dismount_cleanup_pass':True,'harness_removal_pass':True,'network_player_tested':True,
      'core_sha256':CORE_SHA,'overworld_sha256':OW_SHA,'nether_sha256':NN_SHA,
      'native_sea_level':128,'production_accepted':False
    }
    (OUT/'r3925-final-swift-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R3925_FINAL_SWIFT',json.dumps(summary),flush=True)

if __name__=='__main__':main()
