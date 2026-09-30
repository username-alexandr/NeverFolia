#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'test-kit'
b=json.loads((ROOT/'artifacts/build.json').read_text());r=json.loads((ROOT/'artifacts/runtime.json').read_text());assert b['build_pass'] and r['pass']
p=OUT/'world/datapacks';p.mkdir(parents=True);shutil.copyfile(ROOT/'candidate/server.jar',OUT/'server.jar')
for n in ('NeverOverworld.zip','NeverNether.zip'):shutil.copyfile(ROOT/'candidate'/n,p/n)
for n in ('build.json','runtime.json'):shutil.copyfile(ROOT/'artifacts'/n,OUT/n)
(OUT/'eula.txt').write_text('eula=false\n');(OUT/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r3927OceanClassifier=true\n')
(OUT/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\ngamemode=creative\nallow-flight=true\nview-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\n')
(OUT/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
(OUT/'start.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\n')
(OUT/'README-RU.md').write_text('# R39.27 AIR provenance\n\nИспользует vanilla CarvingMask и CAVE_AIR как доказательство пещеры. Крупный неглубокий AIR без cave-provenance может быть восстановлен как океанский объём. Глубокий или небольшой неопределённый AIR остаётся сухим. Y>128 не читается. Только новый тестовый мир.\n')
bins=[OUT/'server.jar',p/'NeverOverworld.zip',p/'NeverNether.zip'];(OUT/'BINARIES.sha256').write_text(''.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(OUT).as_posix()+'\n' for x in bins))
