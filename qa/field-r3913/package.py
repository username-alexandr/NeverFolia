#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';DEST=ROOT/'ice-kit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    b=json.loads((OUT/'r3913-build.json').read_text());r=json.loads((OUT/'r3913-runtime.json').read_text())
    if not (b['build_pass'] and r['pass']):raise ValueError('Current ice build or limited test failed')
    if sha(ROOT/'candidate/server.jar')!=b['candidate_core_sha256']:raise ValueError('Candidate changed')
    DEST.mkdir(exist_ok=False);packs=DEST/'world/datapacks';packs.mkdir(parents=True)
    shutil.copyfile(ROOT/'candidate/server.jar',DEST/'server.jar')
    for name,key in (('NeverOverworld.zip','pack_sha256'),('NeverNether.zip','nether_sha256')):
        source=ROOT/'candidate'/name
        if sha(source)!=b[key]:raise ValueError('Changed source datapack')
        shutil.copyfile(source,packs/name)
    for name in ('r3913-build.json','r3913-runtime.json'):shutil.copyfile(OUT/name,DEST/name)
    provenance={'commit':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'environment':'GitHub Actions','local_r3911_not_used':True,'production_accepted':False}
    (DEST/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    (DEST/'eula.txt').write_text('eula=false\n')
    (DEST/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r399OceanClosure=true\n-Dneverfolia.r3913IceFragments=true\n')
    (DEST/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25613\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nmax-players=4\ngamemode=creative\ndifficulty=normal\nallow-flight=true\nview-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    (DEST/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\njava -version\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
    (DEST/'start.bat').write_bytes(b'@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\njava -version\r\nif errorlevel 1 goto failed\r\npowershell -NoProfile -Command "$ErrorActionPreference=\'Stop\'; foreach($line in Get-Content BINARIES.sha256){ $parts=$line -split \'  \',2; if($parts.Length -ne 2 -or (Get-FileHash -Algorithm SHA256 -LiteralPath $parts[1]).Hash.ToLowerInvariant() -ne $parts[0]){ throw \'Binary checksum mismatch\' } }"\r\nif errorlevel 1 goto failed\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\nexit /b\r\n:failed\r\necho Java or binary verification failed.\r\npause\r\nexit /b 1\r\n')
    changes=r['comparisons']['off_vs_candidate']['changed']
    report=f'''# NeverFolia R39.13 — ограниченная очистка подводного льда

Статус: отдельный тестовый кандидат, НЕ исправление всех перечисленных багов.
Сборка и тесты выполнены GitHub Actions. Доступ к компьютеру пользователя не использован.

## База и сохранность
Эта поставка собрана из GitHub-линии R39.11, восстановленной из точного R39.9. Это НЕ побайтное продолжение ранее выданного локального R39.11: два одноимённых варианта имеют разные хеши. Пакет не перезаписывает старый комплект. Сохраняются расширенная заливка 5×5, зависимости LIGHT, хотфикс снега и постоянная защита шахт. Классы водного прохода и защиты сохранены относительно используемого родителя.
Родительский GitHub JAR: {b['parent_github_r3911_sha256']}
Новый JAR: {b['candidate_core_sha256']}
Локальный прежний R39.11, который НЕ использован: {b['known_local_r3911_sha256']}

## Новое изменение
После океанского прохода оцениваются целые связные фрагменты обычного, плотного и синего льда. Удаление разрешено только для полностью известных внутри текущего чанка небольших компонентов (не более 64 блоков), глубже защитной поверхностной полосы 16 блоков. Все наружные грани должны граничить с водой/водной растительностью; сверху также допускается крышка из магмы. Магма не удаляется, лава не допускается.
Компоненты у неизвестного края чанка, около воздуха/породы, крупные образования и лёд около поверхности сохраняются. Чанки с записанными структурами/ссылками на них или геометрией сухих шахт пропускаются консервативно. Подмороженный лёд не затрагивается. Меняется только ICE/PACKED_ICE/BLUE_ICE → WATER-источник; воздух не создаётся. Снимок проверяется до первой записи. LIGHT/FULL-чанки повторно не изменяются.
Это ограниченная политика удаления подводных остатков, а не доказательство, что любой естественный кусок льда ошибочен. Она не восстанавливает разрушенные айсберги и не чинит автоматически старые чанки. Очень крупные/пограничные/структурные случаи остаются.

## Фактические проверки
19 отдельных сцен на настоящих detached ProtoChunk прошли, включая лёд под магмой, каменный навес, сухой контакт, крупный компонент, границу чанка, отрицательные координаты, сохранённые шахты, ссылку на структуру, LIGHT/FULL, текущую воду и подмороженный лёд. Это не тест конкурентного планировщика на всех нагрузках.
Отдельно исполнены процессы родительского сервера, нового с выключенной очисткой, нового с включённой очисткой и перезапуска кандидата. В каждом изучены те же 27 естественных чанков, seed -4651369264513492755. Сравниваются все 262144 состояния блоков каждого чанка по всей высоте -512..511, а не только количество воды.
Родитель ↔ выключенный кандидат: различий {r['comparisons']['parent_vs_off']['changed']}.
Включение очистки: {changes} замен льда водой; иных различий {r['comparisons']['off_vs_candidate']['unexpected']}.
Кандидат ↔ перезапуск: различий {r['comparisons']['candidate_vs_restart']['changed']}.
Оставшийся лёд во всей целевой выборке: {r['final_candidate_ice_blocks']} блоков. Это не число подтверждённых багов.
Живые полные снимки блоков сравнивает отдельный Python-код. MCA-файлы сохранены после stop, но их содержимое независимо не декодировалось в этом этапе. Block-entity NBT и боевое поведение мобов этим сравнением не проверяются. Клиентский визуальный тест остаётся ручным.
Повторная компиляция новых классов дала те же байты. Унаследованный сборщик выполнил свои тесты решателя и ZIP-упаковщика. Это инкрементальная компиляция, не полная Gradle-сборка.

## Запуск
Распаковать ТОЛЬКО в новую папку. Старое сохранение со скриншотами не удалять и не переносить.
Нужна Java 25. Прочитать Minecraft EULA; при согласии вручную изменить eula=false на eula=true.
Windows: start.bat. Linux: bash start.sh. Скрипты проверяют игровые файлы и передают оба флага из jvm.args.
Адрес на той же машине: localhost:25613. По умолчанию слушается только 127.0.0.1. Для другой тестовой машины нужен SSH-туннель или осознанная смена server-ip с ограничением брандмауэра.
После Done команды консоли: whitelist add НИК; op НИК. Выключение: stop.
Для отдельного сравнения можно выключить только -Dneverfolia.r3913IceFragments=true, заменив true на false, и создать ДРУГОЙ новый мир. Заливку оставлять включённой. Не оценивать эффект на уже готовых чанках.

## Ручная проверка
Проверить районы около -2701 63 -4040 и -3022 62 -3564 на новом мире. Координаты из прежних F3 — позиции камеры, не гарантированный адрес льда. Проверить остатки под магмой и соседние холодные биомы. Не удалять все ледяные структуры вручную.
Дополнение зачарований R39.12 остаётся отдельным клиентским пакетом; оно не менялось. Мобы, ресурсные пробелы данжей и все остаточные океанские полости не объявлены исправленными.

Полные сведения: r3913-build.json, r3913-runtime.json, provenance.json. Проверки Windows-скрипта на самой Windows не проводились.
'''
    (DEST/'README-RU.md').write_text(report,encoding='utf-8');(OUT/'R39.13-report-RU.md').write_text(report,encoding='utf-8')
    binary=[DEST/'server.jar',packs/'NeverOverworld.zip',packs/'NeverNether.zip']
    (DEST/'BINARIES.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(DEST).as_posix()+'\n' for p in binary))
    subprocess.run(['bash','-n',str(DEST/'start.sh')],check=True)
    subprocess.run(['sha256sum','-c','BINARIES.sha256'],cwd=DEST,check=True)
    (DEST/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(DEST).as_posix()+'\n' for p in sorted(DEST.rglob('*')) if p.is_file()))
    print('R3913_PACKAGED '+json.dumps({'server_sha256':b['candidate_core_sha256'],'natural_ice_to_water':changes,'full_worldgen_accepted':False}),flush=True)
if __name__=='__main__':main()
