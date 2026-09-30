#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'test-kit'
build=json.loads((ROOT/'artifacts/build.json').read_text())
runtime=json.loads((ROOT/'artifacts/runtime.json').read_text())
assert build['build_pass'] is True and runtime['pass'] is True
packs=OUT/'world/datapacks';packs.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,packs/n)
for n in ('build.json','runtime.json'):shutil.copyfile(ROOT/'artifacts'/n,OUT/n)
(OUT/'eula.txt').write_text('eula=false\n')
(OUT/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r3926OceanClassifier=true\n')
(OUT/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25612\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nmax-players=2\ngamemode=creative\nallow-flight=true\nview-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\n')
(OUT/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
(OUT/'start.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\n')
(OUT/'README-RU.md').write_text('# NeverFolia R39.26 — ocean/cave classifier\n\nБаза: точный R39.9. Патч не меняет дно, surface rules, растительность, датапаки или зачарования. Новый проход читает только Y=-511..128 и никогда не использует блоки выше уровня моря для решения, заливать ли воздушный объём.\n\nЗакрытые пещеры и сохранённые области шахт остаются сухими. Записывается только AIR -> WATER в чанке-владельце после положительного связного доказательства от плоскости Y=128. Неизвестный соседний чанк не считается океаном.\n\nТолько новый пустой тестовый мир. Старый мир не копировать. После принятия EULA вручную изменить eula=false на eula=true.\n')
binary=[OUT/'server.jar',packs/'NeverOverworld.zip',packs/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(OUT).as_posix()+'\n' for p in binary))
