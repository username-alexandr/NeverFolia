#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'test-kit-r3936'
b=json.loads((ROOT/'artifacts/build-r3936.json').read_text())
r=json.loads((ROOT/'artifacts/runtime-r3936.json').read_text())
assert b['build_pass'] and r['pass']

p=OUT/'world/datapacks';p.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
shutil.copyfile(ROOT/'candidate/NeverOverworld.zip',p/'NeverOverworld.zip')
shutil.copyfile(ROOT/'candidate/NeverNether.zip',p/'NeverNether.zip')
shutil.copyfile(ROOT/'artifacts/build-r3936.json',OUT/'build-r3936.json')
shutil.copyfile(ROOT/'artifacts/runtime-r3936.json',OUT/'runtime-r3936.json')

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
(OUT/'README-RU.md').write_text(
  '# NeverFolia R39.36 — Underground All Heights\n\n'
  'Изменены 8 custom NeverOverworld underground structures: buried_sanctum, '
  'abyssal_archive, ancient_cistern, collapsed_mine, geode_vault, flooded_ruins, '
  'prospector_camp, sealed_cache. Индивидуальные Y-диапазоны удалены. Resolver '
  'может выбрать любую допустимую высоту от Y=-480 до локального OCEAN_FLOOR_WG '
  'минус защитный слой поверхности. Тип окружения каждой структуры сохранён: '
  'толща породы, пол/край пещеры, затопленная подземная полость и т.д. '
  'flooded_ruins больше не использует открытую поверхность/океан. '
  'Ванильные mineshaft/trial_chambers этим релизом не изменены. '
  'R39.34 Monument и R39.35 Ocean Pillar сохранены. Проверять на новом мире.\n',
  encoding='utf-8'
)

bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(
  hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n'
  for x in bins
))
print('R3936_PACKAGE '+json.dumps({
  'server_sha256':hashlib.sha256((OUT/'server.jar').read_bytes()).hexdigest(),
  'pack_sha256':hashlib.sha256((p/'NeverOverworld.zip').read_bytes()).hexdigest()
}))
