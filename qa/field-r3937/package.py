#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'test-kit-r3937'
b=json.loads((ROOT/'artifacts/build-r3937.json').read_text())
r=json.loads((ROOT/'artifacts/runtime-r3937.json').read_text())
assert b['build_pass'] and r['pass']

p=OUT/'world/datapacks';p.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
shutil.copyfile(ROOT/'candidate/NeverOverworld.zip',p/'NeverOverworld.zip')
shutil.copyfile(ROOT/'candidate/NeverNether.zip',p/'NeverNether.zip')
shutil.copyfile(ROOT/'artifacts/build-r3937.json',OUT/'build-r3937.json')
shutil.copyfile(ROOT/'artifacts/runtime-r3937.json',OUT/'runtime-r3937.json')

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
  '# NeverFolia R39.37 — NeverNether Structure Integration\n\n'
  'В NeverNether.zip реально добавлены 20 custom structures из закреплённых '
  'Hearths, Dungeons & Taverns, Explorify, Structory Towers и Better Monuments. '
  'Добавлены 4 NeverFolia structure_set: custom_major, custom_medium, '
  'custom_ambient, nether_monument. Сторонние structure_set и terrain/noise '
  'override не импортируются. Все 20 structure ID подтверждены runtime registry QA. '
  'Ванильные fortress, bastion_remnant, ruined_portal_nether и nether_fossil '
  'сохранены. R39.34–R39.36 Overworld fixes сохранены. Проверять на новом мире.\n',
  encoding='utf-8'
)

bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(
  hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n'
  for x in bins
))
print('R3937_PACKAGE '+json.dumps({
  'server_sha256':hashlib.sha256((OUT/'server.jar').read_bytes()).hexdigest(),
  'overworld_sha256':hashlib.sha256((p/'NeverOverworld.zip').read_bytes()).hexdigest(),
  'nether_sha256':hashlib.sha256((p/'NeverNether.zip').read_bytes()).hexdigest()
}))
