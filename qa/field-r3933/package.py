#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'test-kit-r3933'
b=json.loads((ROOT/'artifacts/build-r3933.json').read_text())
r=json.loads((ROOT/'artifacts/runtime-r3933.json').read_text())
assert b['build_pass'] and r['pass']

p=OUT/'world/datapacks';p.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
shutil.copyfile(ROOT/'candidate/NeverOverworld.zip',p/'NeverOverworld.zip')
shutil.copyfile(ROOT/'candidate/NeverNether.zip',p/'NeverNether.zip')
for src,name in [
    (ROOT/'artifacts/build-r3933.json','build-r3933.json'),
    (ROOT/'artifacts/runtime-r3933.json','runtime-r3933.json')
]: shutil.copyfile(src,OUT/name)

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
(OUT/'README-RU.md').write_text('''# NeverFolia R39.33 — Underwater Water + Trident Seabed

Проверять на НОВОМ мире.

## Маленькие океанские структуры
Высота и привязка НЕ изменялись относительно R39.32.

- structory_towers:ocean_pillar: start_height=0, OCEAN_FLOOR_WG, terrain_adaptation=none.
  Добавлена water-preserve обработка pool-element.
- nova_structures:conduit_ruin: start_height=0, OCEAN_FLOOR_WG, terrain_adaptation=none.
  В conduit_ruin_degradation гарантированы AIR->WATER и CAVE_AIR->WATER при замене существующей воды.

## Крупный Trident Trial Monument
- OCEAN_FLOOR_WG сохранён.
- terrain_adaptation=none: рельеф специально не выравнивается и не вытягивается.
- start_height=-3: основание слегка заглублено относительно дна.
- Перед стартом проверяется дно в сетке 5x5 в радиусе 48 блоков, шаг 24.
- Если перепад OCEAN_FLOOR_WG > 6 блоков, кандидат отвергается.
- Все Trident template-pieces сохраняют существующую воду вместо AIR/CAVE_AIR.

Цель: маленьким структурам чинить только воду; для большого монумента убрать зависание/длинные опоры без порчи морского рельефа.

## Ручная проверка
1. Новый ocean_pillar: посадка как раньше, снаружи нет воздушного выреза.
2. Новый conduit_ruin: посадка как раньше, вода не вырезается.
3. Новый trident_trial_monument: основание немного входит в дно; нет длинных искусственных колонн вниз.
4. Вокруг всех частей Trident нет прямоугольных AIR-полостей.
5. Проверять только новые чанки/новый мир.
''',encoding='utf-8')

bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n' for x in bins))
print('R3933_PACKAGE '+json.dumps({
  'server_sha256':hashlib.sha256((OUT/'server.jar').read_bytes()).hexdigest(),
  'pack_sha256':hashlib.sha256((p/'NeverOverworld.zip').read_bytes()).hexdigest()
}))
