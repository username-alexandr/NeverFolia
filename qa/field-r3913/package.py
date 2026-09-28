#!/usr/bin/env python3
"""Stage a manual candidate only after positive, independently saved field regression."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';DEST=ROOT/'ice-kit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    b=json.loads((OUT/'r3913-build.json').read_text());r=json.loads((OUT/'r3913-runtime.json').read_text());s=json.loads((OUT/'r3913-saved-verification.json').read_text())
    if not (b['build_pass'] and r['pass'] and s['pass'] and s['natural_witness_fixed']==19):raise ValueError('Current positive build/runtime/saved regression failed')
    if sha(ROOT/'candidate/server.jar')!=b['candidate_core_sha256']:raise ValueError('Candidate changed')
    DEST.mkdir(exist_ok=False);packs=DEST/'world/datapacks';packs.mkdir(parents=True)
    shutil.copyfile(ROOT/'candidate/server.jar',DEST/'server.jar')
    for name,key in (('NeverOverworld.zip','pack_sha256'),('NeverNether.zip','nether_sha256')):
        source=ROOT/'candidate'/name
        if sha(source)!=b[key]:raise ValueError('Changed input datapack')
        shutil.copyfile(source,packs/name)
    for name in ('r3913-build.json','r3913-runtime.json','r3913-saved-verification.json'):shutil.copyfile(OUT/name,DEST/name)
    (DEST/'provenance.json').write_text(json.dumps({'commit':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'environment':'GitHub Actions','local_r3911_not_used':True,'production_accepted':False},indent=2)+'\n')
    (DEST/'eula.txt').write_text('eula=false\n')
    (DEST/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r399OceanClosure=true\n-Dneverfolia.r3913IceFragments=true\n')
    (DEST/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nmax-players=4\ngamemode=creative\ndifficulty=normal\nallow-flight=true\nview-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    (DEST/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\njava -version\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
    (DEST/'start.bat').write_bytes(b'@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\njava -version\r\nif errorlevel 1 goto failed\r\npowershell -NoProfile -Command "$ErrorActionPreference=\'Stop\'; foreach($line in Get-Content BINARIES.sha256){ $parts=$line -split \'  \',2; if($parts.Length -ne 2 -or (Get-FileHash -Algorithm SHA256 -LiteralPath $parts[1]).Hash.ToLowerInvariant() -ne $parts[0]){ throw \'Binary checksum mismatch\' } }"\r\nif errorlevel 1 goto failed\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\nexit /b\r\n:failed\r\necho Java or binary verification failed.\r\npause\r\nexit /b 1\r\n')
    changes=s['comparisons']['off_vs_candidate']
    report=f'''# NeverFolia R39.13 v2 — подводный лёд и защита частей построек

Статус: собранный тестовый кандидат. Все баги проекта НЕ объявлены исправленными.
Сборка и новые тесты выполнены в GitHub Actions, без подключения к ПК пользователя.

## Основа
Использована закреплённая GitHub-линия R39.11, восстановленная из проверенного R39.9. Сохраняются заливка 5×5, её зависимости планирования, исправление подводного снега и постоянная защита шахт. Все их классы остаются побайтно прежними относительно используемого родителя. Это НЕ побайтное продолжение отдельно выданного локального R39.11: старый комплект не перезаписывается.

Родительский GitHub JAR: {b['parent_github_r3911_sha256']}
Новый JAR: {b['candidate_core_sha256']}
Прежний локальный R39.11, который не использован: {b['known_local_r3911_sha256']}
NeverOverworld и NeverNether не менялись. Сборка инкрементальная javac 25, не полный Gradle.

## Что изменено
После заливки оцениваются целые связные фрагменты обычного, плотного и синего льда. Удаляются только небольшие компоненты до 64 блоков, глубже полосы 16 блоков у поверхности океана, целиком известные внутри текущего чанка и окружённые водой/водной растительностью. Сверху допускается магма. Создаётся вода-источник, а не воздух. Магма, породы и исходные жидкости не заменяются.

Защита привязана к BoundingBox отдельных частей структур с оболочкой в один блок и к постоянным данным шахт. Подземная постройка больше не блокирует очистку всей водной колонки над ней. Границы получаются только из уже предоставленного кэша держателей чанков; новые соседи не загружаются. Если ссылка на структуру не разрешается, весь чанк консервативно пропускается. Перед записью повторно проверяются защитная маска и все состояния владельца.

Лёд около поверхности, в крупных компонентах, у неизвестного края чанка, рядом со скалой/воздухом/лавой и внутри защиты сохраняется. Подмороженный лёд не затрагивается. FULL/LIGHT-чанки не ремонтируются. Это ограниченная политика подводных остатков, не заявление, что весь естественный лёд ошибочен.

## Реальный результат
Первый вариант R39.13 прошёл синтетические тесты, но дал ноль изменений в природе: защита целого чанка оказалась слишком широкой. Такой результат НЕ принят как исправление полевого бага. Его run 36405033661 и диагностические файлы сохранены.

После чтения настоящих MCA установлено, что над подземными катакомбами остался отдельный погружённый ледяной фрагмент на Y=62. Во второй версии используется защита по фактическим частям вместо целого чанка.

Новые проверки: 21 отдельная синтетическая сцена на настоящих detached ProtoChunk; отдельно родительский сервер, новый с выключенной очисткой, новый с включённой очисткой и перезапуск. У каждого свежий nonce/PASS и штатный stop. Это не нагрузочный тест планировщика.

| Проверка сохранённых MCA, 27 одинаковых целевых чанков | Результат |
|---|---:|
| Полные Name/Properties состояния в каждой паре | {s['states_per_comparison']} |
| Родитель ↔ выключенный кандидат | {s['comparisons']['parent_vs_off']} изменений |
| При включении очистки | {changes} замен льда водой |
| Неожиданные изменения блоков / защищённых клеток | 0 / 0 |
| Воспроизведённый ледяной фрагмент на Y=62 | все 19 клеток заменены водой |
| Кандидат ↔ повторный запуск | {s['comparisons']['candidate_vs_restart']} изменений |
| Отличия snapshot от настоящего сохранения | {s['observed_to_saved_differences']} |
| PDC, границы структур и block-entity NBT | совпали |

Ниже Y=0 количество льда сохранилось: {s['below_zero_ice_preserved']['off']} → {s['below_zero_ice_preserved']['candidate']}. Он не был удалён как мусор. Показатель не означает, что проверены все данжи мира.

MCA-файлы прочитаны отдельным Python NBT-парсером после остановки серверов. Проверены координаты/FULL/все 64 секции; отсутствие данных не заменяется воздухом. Изменённые клетки сверены с сохранёнными частями всех соответствующих структур и границами шахт. Дополнительный QA-плагин не входит в пользовательский архив. Повторная компиляция новых классов дала те же байты; полная повторная Gradle-сборка не выполнялась.

## Что пока остаётся
Ледяные ножки с контактом гравия/камня и компоненты на границах чанков эта версия может сохранять. Удаление всех фрагментов со скриншотов не доказано. Очень большие воздушные полости, полная работа мобов и ресурсные пробелы данжей остаются отдельными задачами. Клиентское дополнение зачарований R39.12 не менялось. Старые миры автоматически не исправляются. Перенос целых айсбергов к новой поверхности моря не выполняется.

## Запуск
Распаковать только в НОВУЮ пустую папку. Старый мир со скриншотами сохранить отдельно.
Java 25 нужна отдельно. Прочитать Minecraft EULA и при согласии вручную изменить eula=false на eula=true.
Windows: start.bat. Linux: bash start.sh. Скрипты проверяют игровые файлы и передают оба флага из jvm.args.
Подключение с той же машины: localhost:25613. По умолчанию сервер слушает только 127.0.0.1; для другой машины нужен туннель или явное изменение server-ip с ограничением брандмауэра.
После Done команды консоли: whitelist add НИК; затем op НИК. Выключение: stop.

Для точечной ручной проверки: /gamemode spectator, затем /tp @s -3013 63 -3556.
Это место фактически проверенного погружённого фрагмента на новом мире с seed -4651369264513492755. Лёд внутри расположенного ниже данжа должен остаться.

Windows-лаунчер не исполнялся на Windows. Полная визуальная проверка клиента и новые тесты обратного порядка генерации не выполнялись. Точный результат: r3913-build.json, r3913-runtime.json, r3913-saved-verification.json.
'''
    (DEST/'README-RU.md').write_text(report,encoding='utf-8');(OUT/'R39.13-report-RU.md').write_text(report,encoding='utf-8')
    binary=[DEST/'server.jar',packs/'NeverOverworld.zip',packs/'NeverNether.zip']
    (DEST/'BINARIES.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(DEST).as_posix()+'\n' for p in binary))
    subprocess.run(['bash','-n',str(DEST/'start.sh')],check=True);subprocess.run(['sha256sum','-c','BINARIES.sha256'],cwd=DEST,check=True)
    (DEST/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(DEST).as_posix()+'\n' for p in sorted(DEST.rglob('*')) if p.is_file()))
    print('R3913_PACKAGED '+json.dumps({'server_sha256':b['candidate_core_sha256'],'natural_ice_to_water':changes,'saved_witness_fixed':19,'full_worldgen_accepted':False}),flush=True)
if __name__=='__main__':main()
