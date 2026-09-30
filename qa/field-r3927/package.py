#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'test-kit'
b=json.loads((ROOT/'artifacts/build.json').read_text());r=json.loads((ROOT/'artifacts/runtime.json').read_text())
assert b['build_pass'] and r['pass']
packs=OUT/'world/datapacks';packs.mkdir(parents=True)
shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,packs/n)
for n in ('build.json','runtime.json'):shutil.copyfile(ROOT/'artifacts'/n,OUT/n)
(OUT/'eula.txt').write_text('eula=false\n')
(OUT/'jvm.args').write_text('-Xms1G\n-Xmx5G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r3927OceanClassifier=true\n-Dneverfolia.r3927StrictAir=true\n')
(OUT/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nmax-players=2\ngamemode=creative\nallow-flight=true\nview-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\n')
(OUT/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
(OUT/'start.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\n')
(OUT/'README-RU.md').write_text('# NeverFolia R39.27 — native-origin ocean check\n\nБаза: R39.26. AIR больше не классифицируется только по BlockState. Используются штатная ProtoChunk CarvingMask, повторный read-only расчёт исходного NoiseChunk и широкий слой нативного океана Y=63 как дополнительный якорь под островами. Блоки выше Y=128 не читаются.\n\nStrict-режим включён: если исходный NoiseChunk недоступен или AIR, который по исходному aquifer должен быть WATER, остаётся воздухом, генерация тестового чанка падает вместо тихого принятия дефекта.\n\nCI сравнил 54 природных чанка с R39.26: допустимы только AIR/CAVE_AIR/VOID_AIR -> source WATER до Y=128; любые изменения дна/камня/льда/растительности/структур запрещены. Только новый пустой тестовый мир.\n')
binary=[OUT/'server.jar',packs/'NeverOverworld.zip',packs/'NeverNether.zip']
(OUT/'BINARIES.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(OUT).as_posix()+'\n' for p in binary))
