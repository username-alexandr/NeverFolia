#!/usr/bin/env python3
"""Strict lifecycle regression reusing the real loopback runner. Original author
behavior remains reproducible in run_runtime.py and its retained failed-cleanup
result. This variant must clear both harness-removal and dismount leftovers.
"""
from pathlib import Path
import json,subprocess,sys,zipfile
import run_runtime as r

def once(text,before,after):
    if text.count(before)!=1:raise ValueError('Unexpected QA anchor '+before[:100])
    return text.replace(before,after,1)

def main():
    report={'pass':False,'production_accepted':False,'scope':'Actual loopback mount/dismount and production enchantment tick entry, server-side key states. No graphical rendering.'}
    try:
        build=json.loads((r.OUT/'swift-build.json').read_text());kernel=json.loads((r.OUT/'swift-kernel.json').read_text())
        r.need(build['pass'] and kernel['pass'],'Missing build')
        new=r.OUT/'NeverOverworld-R3915.zip';fixed=r.OUT/'server-r3915.jar';r.need(r.sha(new)==build['output_sha256'] and r.sha(fixed)==kernel['output_sha256'],'Output changed')
        core=r.exact('server.jar',r.CORE);base=r.exact('NeverOverworld.zip',r.BASE);nether=r.exact('NeverNether.zip',r.NETHER)
        text=(Path(__file__).parent/'R3915SwiftQa.java').read_text()
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
                // Runs the actual patched entry used by the player's next entity tick,
                // not the cleanup helper directly. The rider and mount are still owned.
                Identifier unrelated=Identifier.fromNamespaceAndPath("neverfolia_qa","unrelated_speed");
                fov.addTransientModifier(new AttributeModifier(unrelated,0.123,AttributeModifier.Operation.ADD_MULTIPLIED_BASE));
                EnchantmentHelper.tickEffects(level,driver);
                absent(fov,FOV,"dismount clears rider modifier on player tick "+n);
                amount(fov,unrelated,0.123,"cleanup preserves unrelated modifiers "+n);
                fov.removeModifier(unrelated);''')
        text=once(text,'                // Fixture teardown only, after recording whether real cleanup failed.\n                fov.removeModifier(FOV);',
                  '                absent(fov,FOV,"no fixture repair is needed after dismount "+n);')
        # Runtime source is retained exactly as compiled, not just a patch recipe.
        source=r.WORK/'lifecycle-qa-source';source.mkdir(exist_ok=False);java=source/'R3915SwiftQa.java';java.write_text(text)
        (r.OUT/'R3915SwiftQa-lifecycle.java.txt').write_text(text)
        classes=r.WORK/'lifecycle-qa-classes';classes.mkdir(exist_ok=False);cp=(r.WORK/'classpath.txt').read_text()
        p=subprocess.run(['javac','--release','25','-proc:none','-classpath',cp,'-d',str(classes),str(java)],text=True,capture_output=True)
        (r.OUT/'lifecycle-qa-javac.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr,flush=True);r.need(p.returncode==0,'Lifecycle QA did not compile')
        plugin=r.WORK/'R3915SwiftLifecycleQa.jar'
        with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as z:
            for path in classes.rglob('*.class'):z.write(path,path.relative_to(classes).as_posix())
            z.writestr('plugin.yml',"name: R3915SwiftQa\nversion: '2'\nmain: R3915SwiftQa\napi-version: '26.2'\nfolia-supported: true\n")
        Client,cfg=r.wire_config()
        report['baseline']=r.phase('lifecycle-baseline',core,r.setup('lifecycle-baseline',base,nether,plugin),True,Client,cfg);r.need(report['baseline']['pass'],'Baseline failed')
        folder=r.setup('lifecycle-candidate',new,nether,plugin)
        report['candidate']=r.phase('lifecycle-candidate',fixed,folder,False,Client,cfg);r.need(report['candidate']['pass'],'Candidate failed')
        report['restart']=r.phase('lifecycle-restart',fixed,folder,False,Client,cfg);r.need(report['restart']['pass'],'Restart failed')
        for phase in ('candidate','restart'):
            rows=report[phase]['observed']['levels'];r.need(len(rows)==3 and not any(row['residual_rider_modifier_after_detach'] for row in rows),'Dismount cleanup not complete')
        r.need(r.sha(core)==r.CORE and r.sha(base)==r.BASE and r.sha(nether)==r.NETHER and r.sha(fixed)==kernel['output_sha256'],'Input or kernel changed')
        report.update({'pass':True,'dismount_cleanup_pass':True,'harness_removal_pass':True,'new_core_sha256':kernel['output_sha256'],'new_pack_sha256':build['output_sha256']})
    except Exception as e:report['error']=repr(e)
    finally:r.save('swift-lifecycle-runtime.json',report)
    print('SWIFT_LIFECYCLE',json.dumps({k:v for k,v in report.items() if k not in ('baseline','candidate','restart')}),flush=True)
    r.need(report['pass'],'Lifecycle not accepted')
if __name__=='__main__':main()
