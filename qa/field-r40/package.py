#!/usr/bin/env python3
"""Package completed bounded integration; never marks production accepted."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts';CAND=ROOT/'candidate';KIT=ROOT/'test-kit'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    report=json.loads((OUT/'r40-runtime.json').read_text());build=report['build']
    if report.get('bounded_integration_pass') is not True or report.get('error') or not report.get('inputs_unchanged'):raise ValueError('Unaccepted or incomplete integration')
    if len(report['phases'])!=7 or not all(p.get('pass') is True for p in report['phases'].values()):raise ValueError('Missing completed process')
    KIT.mkdir(exist_ok=False);packs=KIT/'world/datapacks';packs.mkdir(parents=True)
    for name,dest,key in (('server.jar',KIT,'candidate_core_sha256'),('NeverOverworld.zip',packs,'pack_sha256'),('NeverNether.zip',packs,'nether_sha256')):
        source=CAND/name
        if sha(source)!=build[key]:raise ValueError('Changed binary '+name)
        shutil.copyfile(source,dest/name)
        if sha(dest/name)!=build[key]:raise ValueError('Copy checksum mismatch')
    for name in ('build.json','r40-runtime.json','r40-provenance.json'):shutil.copyfile(OUT/name,KIT/name)
    (KIT/'eula.txt').write_text('eula=false\n')
    (KIT/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r395OceanClosure=true\n')
    (KIT/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25610\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\ngamemode=creative\ndifficulty=normal\nallow-flight=true\nmax-players=2\nview-distance=4\nsimulation-distance=3\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    binaries=(KIT/'server.jar',packs/'NeverOverworld.zip',packs/'NeverNether.zip')
    (KIT/'BINARIES.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(KIT).as_posix()+'\n' for p in binaries))
    (KIT/'verify.ps1').write_text('''$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
foreach ($line in Get-Content -LiteralPath "BINARIES.sha256") {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "Invalid checksum row" }
    $expected=$Matches[1]; $path=Join-Path $PSScriptRoot $Matches[2]
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "Checksum mismatch: $path" }
}
Write-Host "Binary checksums OK"
''',encoding='utf-8')
    (KIT/'start.bat').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\npowershell.exe -NoProfile -File "%~dp0verify.ps1"\r\nif errorlevel 1 goto failed\r\njava -version\r\nif errorlevel 1 goto failed\r\njava "@jvm.args" -jar server.jar --nogui\r\n:failed\r\npause\r\n')
    (KIT/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\nsha256sum -c BINARIES.sha256\njava -version\nexec java @jvm.args -jar server.jar --nogui\n')
    (KIT/'README-RU.md').write_text('''# NeverFolia R40 — объединённый кандидат океанской заливки

Ядро R39.9 с сохранёнными хотфиксами снега и защиты шахт. Добавлен и включён в jvm.args экспериментальный проход связности R39.5. Это первый комплект этой ветки с активной заливкой полостей под островами; не полный production-релиз.

## Запуск
Распаковать ТОЛЬКО в новую пустую папку. Старый мир со скриншотами сохранить отдельно, не копировать сюда. В папке world изначально только два датапака. Java 25 устанавливается отдельно. Прочитать Minecraft EULA и при согласии самостоятельно установить eula=true. Windows: start.bat. Linux: bash start.sh. Оба запуска проверяют SHA-256 трёх игровых файлов. При запрете запуска PowerShell в Windows не менять системные политики: проверить BINARIES.sha256 вручную и запустить java "@jvm.args" -jar server.jar --nogui.

Подключение с этой машины: localhost:25610. Для другой машины — SSH-туннель или осознанная настройка server-ip и брандмауэра. В консоли после Done: whitelist add ВАШ_НИК, затем op ВАШ_НИК. Остановка: stop.

В игре проверить /seed: -4651369264513492755. Пример контрольной точки: /gamemode spectator, затем /tp @s 135 62 24; удалённая область: /tp @s -27159 66 -12292. F3 показывает позицию камеры, не координату самого дефекта. Сохранить общий и близкий ракурс до любых изменений блоков.

## Что делает проход
Ищет реальный путь через воздух/воду к открытой сверху океанской колонке, в том числе сбоку под крышей острова. Записывает только AIR -> источник WATER и только в новый центральный чанк. Не меняет существующие жидкости, лёд, камень, растительность и блоки структур. Сохранённые границы частей шахт и их оболочки закрыты для прохода. Полностью закрытые пещеры не получают воду от одного наличия подземного озера.

Поиск ограничен 3x3 чанками; выход за пределы кэша остаётся недоказанным. Крупные полости с удалённым выходом могут сохраниться. Чтение FEATURES-соседей не является доказательством неизменяемого глобального снимка. Произвольные сухие помещения других данжей не все имеют защитную маску. Полнота устранения дефектов со скриншотов не принята.

## Проверки
Десять синтетических сцен на настоящих ProtoChunk, BlockState и PDC; держатели кэша являются тестовыми адаптерами, а не живым планировщиком. Все блоки владельца и соседей сравниваются. Естественные прогоны отдельно используют реальный планировщик Folia и обычную генерацию: R39.9, R40 выключен, R40 включён, оба ядра в обратном порядке и перезапуск кандидата. Точные результаты в r40-runtime.json. Межпорядковая изменчивость исходной FEATURES-генерации остаётся отдельным открытым вопросом; прежний строгий gate R397 не отменён.

Сборка инкрементальная javac --release 25, не полная Gradle. Ни QA-плагины, ни тестовые сохранения в комплект не входят. Лёд, интерфейс зачарований и 95 прежних отсутствующих шаблонов этим этапом не исправлены. Сохранённые повреждённые чанки автоматически не ремонтируются. Рабочий сервер этим архивом не заменять.
''',encoding='utf-8')
    (KIT/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(KIT).as_posix()+'\n' for p in sorted(KIT.rglob('*')) if p.is_file()))
    for line in (KIT/'SHA256SUMS.txt').read_text().splitlines():
        expected,name=line.split('  ',1)
        if sha(KIT/name)!=expected:raise ValueError('Kit self verification failed')
    print('R40_TEST_KIT_READY',build['candidate_core_sha256'])
if __name__=='__main__':main()
