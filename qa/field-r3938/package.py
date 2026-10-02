#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'test-kit-r3938'
b=json.loads((ROOT/'artifacts/build-r3938.json').read_text())
r=json.loads((ROOT/'artifacts/runtime-r3938.json').read_text())
assert b['build_pass'] and r['pass']

p=OUT/'world/datapacks';p.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
shutil.copyfile(ROOT/'candidate/NeverOverworld.zip',p/'NeverOverworld.zip')
shutil.copyfile(ROOT/'candidate/NeverNether.zip',p/'NeverNether.zip')
shutil.copyfile(ROOT/'artifacts/build-r3938.json',OUT/'build-r3938.json')
shutil.copyfile(ROOT/'artifacts/runtime-r3938.json',OUT/'runtime-r3938.json')

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
(OUT/'README-RU.md').write_text(
  '# NeverFolia R39.38 — NeverNether Locate/Placement Performance\n\n'
  'Исправляет зависание /locate structure для 20 custom NeverNether structures. '
  'Стандартный vanilla/Folia locate path сохранён: он по-прежнему выполняет '
  'полные Jigsaw, biome и dimension-padding проверки и возвращает только '
  'действительно генерируемый кандидат. Оптимизирован общий '
  'NeverNetherStructurePlacement.resolveStartY: вместо полного getBaseColumn '
  'на каждом кандидате используется bounded final-density scan с точечной '
  'интерполяционной проверкой. Тот же resolver используется и locate, и '
  'обычной генерацией, поэтому отдельного приближённого locate predictor нет. '
  'Runtime QA требует locate <4 секунд и затем генерирует найденный chunk, '
  'проверяя что nova_structures:nether_keep действительно появился. '
  'NeverNether.zip R39.37 и NeverOverworld.zip R39.36 не меняются.\n',
  encoding='utf-8'
)

bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(
  hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n'
  for x in bins
))
print('R3938_PACKAGE '+json.dumps({
  'server_sha256':hashlib.sha256((OUT/'server.jar').read_bytes()).hexdigest(),
  'overworld_sha256':hashlib.sha256((p/'NeverOverworld.zip').read_bytes()).hexdigest(),
  'nether_sha256':hashlib.sha256((p/'NeverNether.zip').read_bytes()).hexdigest()
}))
