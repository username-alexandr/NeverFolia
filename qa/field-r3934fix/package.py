#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'test-kit-r3934'
b=json.loads((ROOT/'artifacts/build-r3934.json').read_text())
r=json.loads((ROOT/'artifacts/runtime-r3934.json').read_text())
assert b['build_pass'] and r['pass']

p=OUT/'world/datapacks';p.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
shutil.copyfile(ROOT/'candidate/NeverOverworld.zip',p/'NeverOverworld.zip')
shutil.copyfile(ROOT/'candidate/NeverNether.zip',p/'NeverNether.zip')
shutil.copyfile(ROOT/'artifacts/build-r3934.json',OUT/'build-r3934.json')
shutil.copyfile(ROOT/'artifacts/runtime-r3934.json',OUT/'runtime-r3934.json')

(OUT/'eula.txt').write_text('eula=false\n')
(OUT/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n')
(OUT/'server.properties').write_text(
  'level-name=world\n'
  'level-seed=-4651369264513492755\n'
  'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
  'server-ip=127.0.0.1\nserver-port=25614\nonline-mode=true\n'
  'white-list=true\nenforce-whitelist=true\ngamemode=creative\nallow-flight=true\n'
  'view-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\n'
)
(OUT/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
(OUT/'start.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\n')
(OUT/'README-RU.md').write_text('''# NeverFolia R39.34 — Monument + Ocean Pillar

Исправление Monument:
- огромные призмариновые колонны около -3443 / -3392 создавал vanilla minecraft:monument;
- старый NeverFolia-патч принудительно держал основание на Y=104;
- R39.34 проверяет OCEAN_FLOOR_WG под полным footprint Monument;
- если перепад дна > 12 блоков, кандидат Monument отклоняется;
- если место подходит, основание рассчитывается около реального дна;
- искусственная платформа для выравнивания рельефа не создаётся.

Исправление structory_towers:ocean_pillar:
- 8 удалённых от основной башни template-cells на local x=10, y=21..23, z=5..7
  полностью удалены из NBT blocks list;
- они больше не становятся ни structure_void, ни явным minecraft:water;
- этот объём мира структура вообще не трогает;
- поэтому естественная океанская вода должна оставаться непрерывной без отдельного прямоугольного куба.

NeverNether.zip не изменён.

Проверять на НОВОМ мире.
Контроль:
- около -3443 113 -3392 плохой Monument-кандидат не должен появиться;
- около -3146 69 -3446 должен быть обычный естественный water/aquatic block,
  без structure_void и без отдельного принудительно размещённого водного куба.
''',encoding='utf-8')

bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(
  hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n' for x in bins
))
print('R3934_PACKAGE '+json.dumps({
  'server_sha256':hashlib.sha256((OUT/'server.jar').read_bytes()).hexdigest(),
  'pack_sha256':hashlib.sha256((p/'NeverOverworld.zip').read_bytes()).hexdigest()
}))
