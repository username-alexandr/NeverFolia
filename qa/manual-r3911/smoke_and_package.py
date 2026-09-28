#!/usr/bin/env python3
"""Bounded startup/chunk-generation check, followed by an explicitly MANUAL kit.
No visual or complete world-generation acceptance is implied.
"""
from pathlib import Path
import hashlib,json,os,queue,secrets,shutil,subprocess,threading,time,zipfile
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'artifacts'; WORK=ROOT/'.work/manual-r3911'; CAND=ROOT/'candidate'
SEED=-4651369264513492755
JAVA=r'''import com.google.gson.*;
import java.nio.file.*;
import org.bukkit.*;
import org.bukkit.event.*;
import org.bukkit.event.server.ServerLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
public final class ManualOceanSmoke extends JavaPlugin implements Listener {
 private World world; private int index; private boolean started,finished;
 private final JsonArray rows=new JsonArray();
 private final String nonce=System.getProperty("neverfolia.manualNonce","");
 private final int[][] targets={{7,1},{-196,-218},{-196,-217},{-202,-213},{-1699,-769}};
 @Override public void onEnable(){Bukkit.getPluginManager().registerEvents(this,this);}
 @EventHandler public void loaded(ServerLoadEvent e){
  if(started)return;started=true;
  try{
   if(nonce.isEmpty())throw new IllegalStateException("Missing process nonce");
   world=Bukkit.getWorlds().stream().filter(w->w.getEnvironment()==World.Environment.NORMAL).findFirst().orElseThrow();
   if(world.getSeed()!=-4651369264513492755L)throw new IllegalStateException("Wrong actual seed");
   next();
  }catch(Throwable failure){finish(failure);}
 }
 private void next(){
  if(finished)return;
  if(index==targets.length){finish(null);return;}
  int x=targets[index][0],z=targets[index][1];
  world.getChunkAtAsync(x,z,true).whenComplete((chunk,error)->{
   if(error!=null){finish(error);return;}
   Bukkit.getRegionScheduler().execute(this,world,x,z,()->{
    try{
     ChunkSnapshot snap=chunk.getChunkSnapshot(false,false,false);int air=0,water=0;
     for(int y=60;y<=128;y++)for(int lz=0;lz<16;lz++)for(int lx=0;lx<16;lx++){
      Material t=snap.getBlockType(lx,y,lz);if(t.isAir())air++;if(t==Material.WATER)water++;
     }
     JsonObject row=new JsonObject();row.addProperty("chunk_x",x);row.addProperty("chunk_z",z);
     row.addProperty("air_y60_128",air);row.addProperty("water_y60_128",water);rows.add(row);index++;
     getLogger().info("MANUAL_SMOKE_CHUNK "+x+","+z);
     Bukkit.getGlobalRegionScheduler().execute(this,()->next());
    }catch(Throwable failure){finish(failure);}
   });
  });
 }
 private synchronized void finish(Throwable error){
  if(finished)return;finished=true;JsonObject r=new JsonObject();r.addProperty("pass",error==null);
  r.addProperty("nonce",nonce);r.addProperty("seed",world==null?0:world.getSeed());r.add("chunks",rows);
  r.addProperty("visual_tested",false);r.addProperty("scope","Startup, five requested real chunks and their dependencies; counters are observations, not a defect oracle");
  if(error!=null){r.addProperty("error",error.toString());error.printStackTrace();}
  try{getDataFolder().mkdirs();Files.writeString(getDataFolder().toPath().resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(r));}
  catch(Exception failure){failure.printStackTrace();error=failure;}
  getLogger().info("MANUAL_SMOKE "+(error==null?"PASS ":"FAIL ")+nonce);
 }
}
'''
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def smoke(folder,name):
    nonce=secrets.token_hex(16);events=queue.Queue();lines=[];proc=None;reader=None
    result={'pass':False,'nonce':nonce,'name':name,'visual_tested':False}
    target=folder/'plugins/ManualOceanSmoke/result.json'
    if target.exists():target.rename(OUT/(name+'-previous-result.json'))
    try:
        cmd=['java','-XX:ActiveProcessorCount=4','-Xms512M','-Xmx4G','-Dneverfolia.r399OceanClosure=true','-Dneverfolia.manualNonce='+nonce,'-jar',str(CAND/'server.jar'),'--nogui']
        proc=subprocess.Popen(cmd,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        def pump():
            with (OUT/(name+'.log')).open('w',encoding='utf-8') as stream:
                for line in proc.stdout:stream.write(line);stream.flush();lines.append(line);events.put(line)
            events.put(None)
        reader=threading.Thread(target=pump,daemon=True);reader.start();deadline=time.monotonic()+420;done=False;passed=False
        while time.monotonic()<deadline:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            if 'MANUAL_SMOKE' in line:print(name,line.rstrip(),flush=True)
            if 'MANUAL_SMOKE FAIL '+nonce in line:raise ValueError('Current Java smoke failed')
            if 'MANUAL_SMOKE PASS '+nonce in line:passed=True
            if 'Done (' in line:done=True
            if passed and done:break
        need(done and passed,'Startup/generation did not finish within 420 seconds')
        r=json.loads(target.read_text());need(r.get('pass') is True and r.get('nonce')==nonce and r.get('seed')==SEED,'Wrong or stale report')
        need([(q['chunk_x'],q['chunk_z']) for q in r['chunks']]==[(7,1),(-196,-218),(-196,-217),(-202,-213),(-1699,-769)],'Incomplete chunk generation')
        result['observed']=r;proc.stdin.write('stop\n');proc.stdin.flush();code=proc.wait(timeout=120);reader.join(timeout=15)
        need(code==0 and not reader.is_alive(),'Unclean shutdown/log stream')
        bad=('Failed to load registries','Failed to load datapacks','Overworld settings missing','Chunk system error','requires completed FEATURES','owning snapshot changed before commit','Exception in server tick loop')
        errors=[l.strip() for l in lines if any(t in l for t in bad)];result['targeted_errors']=errors;need(not errors,'Targeted startup or chunk error')
        result['exit_code']=code;result['pass']=True
    except Exception as error:result['error']=repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.stdin.write('stop\n');proc.stdin.flush();proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        if reader is not None:reader.join(timeout=10)
        save(OUT/(name+'.json'),result)
    print('R3911_SMOKE '+json.dumps({k:v for k,v in result.items() if k!='observed'}),flush=True)
    need(result['pass'],'Bounded smoke failed; no runnable kit published');return result

def main():
    build=json.loads((OUT/'build.json').read_text());need(build['build_pass'] is True and sha(CAND/'server.jar')==build['candidate_core_sha256'],'Wrong compiled candidate')
    cp=(WORK/'classpath.txt').read_text();source=WORK/'ManualOceanSmoke.java';source.write_text(JAVA);classes=WORK/'smoke-classes';classes.mkdir()
    p=subprocess.run(['javac','--release','25','-proc:none','-cp',cp,'-d',str(classes),str(source)],text=True,capture_output=True,timeout=90)
    (OUT/'smoke-javac.log').write_text(p.stdout+p.stderr);need(p.returncode==0,'Smoke plugin compilation failed')
    folder=WORK/'smoke-world';packs=folder/'world/datapacks';packs.mkdir(parents=True,exist_ok=False);plugins=folder/'plugins';plugins.mkdir()
    for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(CAND/name,packs/name)
    with zipfile.ZipFile(plugins/'ManualOceanSmoke.jar','w',zipfile.ZIP_DEFLATED) as z:
        for p in classes.rglob('*.class'):z.write(p,p.relative_to(classes).as_posix())
        z.writestr('plugin.yml',"name: ManualOceanSmoke\nversion: '1'\nmain: ManualOceanSmoke\napi-version: '26.2'\nfolia-supported: true\n")
    (folder/'eula.txt').write_text('eula=true\n')
    (folder/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25611\nonline-mode=true\nview-distance=2\nsimulation-distance=2\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    result={'pass':False,'scope':'Compilation, five natural chunk requests and clean restart only; manual worldgen acceptance still required','production_accepted':False,'phases':{}}
    result['phases']['first']=smoke(folder,'smoke-first');result['phases']['restart']=smoke(folder,'smoke-restart')
    result['pass']=True;save(OUT/'smoke.json',result)
    kit=ROOT/'manual-kit';kit.mkdir(exist_ok=False);kp=kit/'world/datapacks';kp.mkdir(parents=True)
    shutil.copyfile(CAND/'server.jar',kit/'server.jar')
    for name in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(CAND/name,kp/name)
    for name in ('build.json','smoke.json'):shutil.copyfile(OUT/name,kit/name)
    provenance={'commit':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),'build_environment':'GitHub Actions','local_chat_executor_available':False,'no_user_device_connection':True,'production_accepted':False}
    save(kit/'provenance.json',provenance)
    (kit/'eula.txt').write_text('eula=false\n')
    (kit/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-XX:ActiveProcessorCount=4\n-Dfile.encoding=UTF-8\n-Dneverfolia.r399OceanClosure=true\n')
    (kit/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=\nserver-port=25611\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nmax-players=4\ngamemode=creative\ndifficulty=normal\nallow-flight=true\nview-distance=6\nsimulation-distance=3\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    (kit/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\njava -version\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
    (kit/'start.bat').write_bytes(b'@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\njava -version\r\nif errorlevel 1 goto failed\r\npowershell -NoProfile -Command "$ErrorActionPreference=\'Stop\'; foreach($line in Get-Content BINARIES.sha256){ $parts=$line -split \'  \',2; if($parts.Length -ne 2 -or (Get-FileHash -Algorithm SHA256 -LiteralPath $parts[1]).Hash.ToLowerInvariant() -ne $parts[0]){ throw \'Binary checksum mismatch\' } }"\r\nif errorlevel 1 goto failed\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\nexit /b\r\n:failed\r\necho Java or binary verification failed. No server started.\r\npause\r\nexit /b 1\r\n')
    subprocess.run(['bash','-n',str(kit/'start.sh')],check=True)
    (kit/'README-RU.md').write_text('''# NeverFolia R39.11 — ручной тест расширенной заливки

Это новый тестовый кандидат, не заявление «все баги исправлены».
Собран на GitHub Actions без подключения компьютера пользователя. Локальный исполнитель чата недоступен.

## Изменения относительно выданного R39.10
- Поиск бокового выхода из полости в океан расширен с 3×3 до 5×5 чанков.
- LIGHT требует завершённых FEATURES в радиусе 3, так как декораторы внешнего ряда могут писать в исследуемый участок.
- Весь снимок центрального чанка проверяется до первой записи. При конфликте нет частичного применения.
- Лава остаётся барьером даже внутри защитной геометрии.
- Бинарная база — точный R39.9. Классы исправления снега и постоянной защиты шахт сохранены побайтно.
- Датапаки не изменены: NeverOverworld R39.3 и согласованный NeverNether.

## Что проверено автоматически
Компиляция настоящим javac 25, тесты чистого алгоритма и ZIP-упаковщика, загрузка пяти контрольных чанков с новой цепочкой зависимостей, штатное выключение и повторный старт того же тестового мира. Подробности в build.json и smoke.json. Это НЕ полная проверка рельефа, льда, всех данжей или мобов. Старые отрицательные результаты независимости генерации от порядка не отменяются.

## Запуск
1. Распаковать только в НОВУЮ пустую папку. Не копировать старый мир.
2. Требуется Java 25. Прочитать Minecraft EULA; при согласии изменить eula=false на eula=true.
3. Windows: start.bat. Linux: bash start.sh.
4. Подключение с той же машины: localhost:25611; с другой: IP тестовой машины:25611. Доступ ограничить брандмауэром тестовой сети.
5. После Done в консоли: whitelist add ВАШ_НИК, затем op ВАШ_НИК.
6. Выключение только командой stop.

Не запускать java -jar без jvm.args: новый проход требует -Dneverfolia.r399OceanClosure=true. Старый флаг r395 не включает этот новый класс.
Seed: -4651369264513492755. Память: 1–4 ГБ, меняется в jvm.args.

## Ручная проверка
Сначала /seed. Затем осмотр в spectator: /tp @s 135 62 24; /tp @s -3041 63 -3455; /tp @s -3217 46 -3398; /tp @s -27167 87 -12324.
Мобов проверять отдельно в survival у нетронутых спавнеров.
Для дефекта нужны координаты, скриншот F3 и logs/latest.log. Старый мир со скриншотами не удалять.

## Не исправлено и не обещается
Конечное окно 5×5 всё ещё может не найти очень дальний выход. Результат порядка FEATURES, все сухие комнаты сторонних данжей, льдинки и клиентское отображение зачарований не приняты. Прежние 95 недостающих шаблонов не восстановлены этим архивом. Старые чанки не ремонтируются. Рост радиуса увеличивает объём генерации. Windows-лаунчер подготовлен, но не исполнен на Windows. Инкрементальный javac, не полная сборка Gradle. QA-плагин и тестовый сохранённый мир НЕ включены.
''',encoding='utf-8')
    (kit/'BUG-REPORT-RU.md').write_text('Версия: R39.11\nSeed из /seed:\nБаг:\nКоординаты дефекта:\nПосле перезапуска:\nПриложить F3 и logs/latest.log.\n',encoding='utf-8')
    binaries=[kit/'server.jar',kp/'NeverOverworld.zip',kp/'NeverNether.zip']
    (kit/'BINARIES.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(kit).as_posix()+'\n' for p in binaries))
    (kit/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(kit).as_posix()+'\n' for p in sorted(kit.rglob('*')) if p.is_file()))
    need(sha(kit/'server.jar')==build['candidate_core_sha256'],'Packaged JAR mismatch')
    need(sha(kp/'NeverOverworld.zip')==build['pack_sha256'] and sha(kp/'NeverNether.zip')==build['nether_sha256'],'Packaged datapack mismatch')
    need({p.relative_to(kit/'world').as_posix() for p in (kit/'world').rglob('*') if p.is_file()}=={'datapacks/NeverOverworld.zip','datapacks/NeverNether.zip'},'Saved world accidentally included')
    out=ROOT/'delivery';out.mkdir(exist_ok=False)
    archive=out/'NeverFolia-R39.11-Manual-TEST.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(kit.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(kit).as_posix())
    with zipfile.ZipFile(archive) as z:
        need(z.testzip() is None,'Delivery CRC failed')
        for line in z.read('SHA256SUMS.txt').decode().splitlines():
            expected,name=line.split('  ',1);need(hashlib.sha256(z.read(name)).hexdigest()==expected,'Delivery file hash mismatch')
    save(OUT/'delivery.json',{'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'build':build,'smoke_pass':True,'manual_acceptance_pending':True,'production_accepted':False})
    print('R3911_DELIVERY '+json.dumps(json.loads((OUT/'delivery.json').read_text())),flush=True)
if __name__=='__main__':main()
