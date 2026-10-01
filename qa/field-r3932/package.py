#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'test-kit-r3932'
b=json.loads((ROOT/'artifacts/build-r3932.json').read_text())
r=json.loads((ROOT/'artifacts/runtime-r3932.json').read_text())
assert b['build_pass'] and r['pass']

p=OUT/'world/datapacks';p.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
shutil.copyfile(ROOT/'candidate/NeverOverworld.zip',p/'NeverOverworld.zip')
shutil.copyfile(ROOT/'candidate/NeverNether.zip',p/'NeverNether.zip')
for src,name in [
    (ROOT/'artifacts/build-r3932.json','build-r3932.json'),
    (ROOT/'artifacts/runtime-r3932.json','runtime-r3932.json')
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
(OUT/'README-RU.md').write_text('''# NeverFolia R39.32 — Underwater Structure Audit

Проверять только на НОВОМ мире.

Исправления:
- structory_towers:ocean_pillar — OCEAN_FLOOR_WG, без beard terrain, внешний cave_air уже заменён на structure_void;
- nova_structures:conduit_ruin — OCEAN_FLOOR_WG с нулевым вертикальным смещением;
- nova_structures:trident_trial_monument — вместо фиксированного Y=41 теперь OCEAN_FLOOR_WG с нулевым смещением;
- все Trident Monument template-pieces получают water-preserve processor: AIR/CAVE_AIR не вытесняет существующую океанскую воду;
- neverfolia:ancient_cistern больше не допускается в открытой толще океана: WATER_BOUNDARY требует каменный потолок и остаётся только подземной затопленной структурой.

R39.31 native sea=128 и отключение позднего synthetic flood сохранены.

Ручная проверка:
1. Найти новый ocean_pillar.
2. Найти новый conduit_ruin.
3. Найти новый trident_trial_monument.
4. Проверить, что все три стоят относительно реального дна, а не фиксированного Y.
5. На прежних координатах ancient_cistern искать новый экземпляр: в открытом океане он больше появляться не должен.
6. Старые чанки не являются проверкой — структуры в них уже записаны.
''',encoding='utf-8')
bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n' for x in bins))
print('R3932_PACKAGE '+json.dumps({'server_sha256':hashlib.sha256((OUT/'server.jar').read_bytes()).hexdigest(),'pack_sha256':hashlib.sha256((p/'NeverOverworld.zip').read_bytes()).hexdigest()}))
