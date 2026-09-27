#!/usr/bin/env python3
"""Package previously tested binaries only; do not rebuild or modify the engine."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

EXPECTED = {
    'server.jar': '411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32',
    'world/datapacks/NeverOverworld.zip': 'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be',
    'world/datapacks/NeverNether.zip': '5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10',
}
FP = '24d1e22d76bc77aa990a1c0e0910e8bbc2ca186be52f4db2a3382ea5b694d7e0'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def find_exact(folder, pattern, digest):
    found = [p for p in Path(folder).rglob(pattern) if p.is_file() and sha(p) == digest]
    if len(found) != 1:
        raise ValueError(f'Expected exactly one matching input: {folder}/{pattern}: {found}')
    return found[0]

def write(root, name, content, executable=False):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')
    if executable:
        path.chmod(0o755)

LINUX = r'''#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v sha256sum >/dev/null 2>&1; then
  echo 'ERROR: sha256sum is required (Linux coreutils).'; exit 1
fi
sha256sum -c CORE-SHA256SUMS.txt || { echo 'ERROR: Core or datapack bytes differ. Do not mix releases.'; exit 1; }
if ! grep -Eq '^[[:space:]]*eula=true[[:space:]]*$' eula.txt; then
  echo 'EULA_NOT_ACCEPTED: Read README-RU.md and the Minecraft EULA, then set eula=true in eula.txt.'
  exit 1
fi
if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/java" ]]; then
  JAVA="$JAVA_HOME/bin/java"
else
  JAVA="$(command -v java || true)"
fi
if [[ -z "$JAVA" ]]; then echo 'ERROR: Install Java 25, or set JAVA_HOME to your Java 25 directory.'; exit 1; fi
VERSION="$($JAVA -version 2>&1)"
if [[ ! "$VERSION" =~ version[[:space:]]+\"25([.\"-]) ]]; then
  printf '%s\n' "$VERSION"
  echo 'ERROR: This exact test kit requires Java 25.'; exit 1
fi
if [[ "${1:-}" == '--check' ]]; then echo 'PRECHECK_OK'; exit 0; fi
if [[ $# -gt 0 ]]; then echo 'Usage: bash start.sh [--check]'; exit 1; fi
echo 'NeverFolia manual test: port 25599; whitelist enabled; heap settings in jvm.args.'
echo 'Use the console command stop for a clean shutdown.'
exec "$JAVA" @jvm.args -jar server.jar --nogui
'''

WINDOWS = r'''param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    foreach ($line in Get-Content -LiteralPath 'CORE-SHA256SUMS.txt') {
        if ($line -notmatch '^([a-f0-9]{64})  (.+)$') { throw 'Invalid checksum manifest.' }
        $expected = $Matches[1]
        $relative = $Matches[2]
        $file = Join-Path $PSScriptRoot $relative
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw ('Core or datapack bytes differ: ' + $relative + '. Do not mix releases.')
        }
    }
    if (-not (Get-Content -LiteralPath 'eula.txt' | Where-Object { $_ -match '^\s*eula=true\s*$' })) {
        throw 'EULA_NOT_ACCEPTED: Read README-RU.md and the Minecraft EULA, then set eula=true in eula.txt.'
    }
    $java = $null
    if ($env:JAVA_HOME) {
        $fromHome = Join-Path $env:JAVA_HOME 'bin/java.exe'
        if (Test-Path -LiteralPath $fromHome) { $java = $fromHome }
    }
    if (-not $java) { $java = (Get-Command java -CommandType Application -ErrorAction Stop).Source }
    # Native java writes -version to stderr, including on success in Windows PowerShell 5.1.
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $java
    $info.Arguments = '-version'
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.CreateNoWindow = $true
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $info
    if (-not $p.Start()) { throw 'Cannot start Java.' }
    $version = $p.StandardError.ReadToEnd() + $p.StandardOutput.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -ne 0 -or $version -notmatch 'version\s+"25[.\"-]') {
        throw ('This exact kit requires Java 25. Detected: ' + $version)
    }
    if ($CheckOnly) { Write-Host 'PRECHECK_OK'; exit 0 }
    Write-Host 'NeverFolia manual test: port 25599; whitelist enabled; heap settings in jvm.args.'
    Write-Host 'Use the console command stop for a clean shutdown.'
    & $java '@jvm.args' '-jar' 'server.jar' '--nogui'
    exit $LASTEXITCODE
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message)
    exit 1
}
'''

README = '''# NeverFolia — готовый комплект для ручного теста R39.3

Это тестовый комплект, не исправленный финальный релиз. Ядро R38 и полный
NeverOverworld R39.3 ранее совместно прошли настоящий запуск и повторный запуск
Java 25. Файлы взяты из тех же CI-артефактов и сохранены байт-в-байт.
Незавершённые изменения R39.4 сюда не включены. Вода и мобы требуют вашей проверки.

## Что внутри
- server.jar — готовое ядро, не исходники и не BASELINE-NOT-R38.
- world/datapacks/NeverOverworld.zip — полный R39.3, включая R39.1/R39.2.
- world/datapacks/NeverNether.zip — согласованный неизменённый пакет.
- start.sh — Linux, start.bat + start.ps1 — Windows.
- jvm.args — общая настройка памяти: минимум 1 ГБ, максимум 4 ГБ heap.
- server.properties, eula.txt, контрольные суммы и протоколы предыдущего CI.

Java 25 устанавливается отдельно. Python, Gradle и ручная сборка не нужны.
При первом запуске может понадобиться интернет для загрузки компонентов ядра.
Архив содержит датапаки в каталоге world, но НЕ содержит заранее созданных чанков
или level.dat: мир генерируется на тестовой машине.

## Первый запуск
1. Распаковать В НОВУЮ ПУСТУЮ ПАПКУ отдельной тестовой машины.
   Ничего из рабочего сервера, старые миры, плагины, overlay-паки или lock-файлы
   туда не копировать. Старые квадраты не исправляются заменой файла ядра.
2. Проверить `java -version`: требуется Java 25. При нескольких установках задать
   JAVA_HOME на каталог Java 25. Не распаковывать ядро из server.jar.
3. Самостоятельно прочитать Minecraft EULA: https://aka.ms/MinecraftEULA
   При согласии заменить `eula=false` на `eula=true` в eula.txt.
4. Linux: `bash start.sh`. Windows: двойной щелчок start.bat.
   Предварительная проверка без запуска: Linux `bash start.sh --check`;
   Windows `powershell -NoProfile -ExecutionPolicy Bypass -File .\\start.ps1 -CheckOnly`.
5. Дождаться строки `Done`. В КОНСОЛИ сервера, без начального `/`, выполнить:
   `whitelist add ВАШ_НИК`
   `op ВАШ_НИК`
6. Подключиться совместимым клиентом Minecraft Java 26.2: с этой же машины
   `localhost:25599`, с другой машины — `IP_ТЕСТОВОЙ_МАШИНЫ:25599`.
   Для LAN разрешить входящий TCP 25599 в локальном firewall при необходимости.
   Не требуется открывать тестовый сервер всему интернету.
7. Останавливать командой `stop` в консоли, а не закрытием окна или kill.

Список допуска включён, online-mode=true: вход по лицензированной учётной записи.
Оператора и первого игрока нужно добавить вручную; ник заранее не предполагался.
Сервер слушает интерфейсы тестовой машины, не только 127.0.0.1.
Секретов, паролей, токенов, RCON и автопубликации в комплекте нет.

## Параметры
Seed: -4651369264513492755
Порт: 25599
level-name: world
max-players: 5
Режим по умолчанию: creative; сложность normal; allow-flight=true.
view-distance=6; simulation-distance=4.
Содержимое мира: обычная тестовая генерация NeverFolia; плагины не установлены.

Память меняется в jvm.args: строка -Xmx4G задаёт потолок heap, но системе и
нативной памяти Java нужно дополнительное место. Для машины с 8 ГБ RAM этот
профиль оставляет около половины памяти вне heap; не выделять серверу всю RAM.
Две программы запуска используют один и тот же jvm.args.

## Ручная проверка
В чате Minecraft команды начинаются с `/`:
`/gamemode spectator` — осмотр воды, чанков, пещер и оснований построек.
`/tp ВАШ_НИК -3217 46 -3398` — ранее отмеченный участок; положение данжа в новой
генерации и его идентичность исходному скриншоту необходимо проверить на месте.
`/gamemode survival` — проверка активации спавнеров. Creative/spectator не
использовать как отрицательный тест появления trial-мобов. Сложность не peaceful.
В исходном CI мобы проверялись лишь в отдельных стендовых конфигурациях, не во всех
естественно размещённых данжах. В этом комплекте игрок и генерация проверяются вручную.

При квадрате воды зафиксировать координаты, подойти с другой стороны, сохранить
сервер командой stop, запустить заново и повторить осмотр той же точки. Для другого
порядка генерации распаковать ещё одну НОВУЮ копию комплекта; старую не удалять.
При испытании данжа сохранить внешний вид спавнера и точные координаты.

Пришлите заполненный BUG-REPORT-RU.md, скриншот с F3 и logs/latest.log после
воспроизведения. Область region и сущности можно запросить отдельно; весь мир
сразу отправлять не нужно. Логи могут содержать никнеймы и адреса игроков — перед
передачей проверьте их на персональную информацию.

## Что не закрыто
Остаются 95 отсутствующих шаблонов: особенно Stray Fort, повозки таверн и
Lone Citadel. Поэтому пустая часть отдельной структуры ещё возможна.
Квадраты воды и все способности мобов не объявляются исправленными.
Встроенный водный аудит R38 ограничен прежней областью возле спавна;
удалённый данж -3217 / 46 / -3398 им не охвачен. Это не мешает ручному осмотру.
Комплект не удаляет искусственные основания из старых сохранённых чанков.
Не использовать как автоматическое обновление рабочего сервера.

## Происхождение
Ядро R38: c6e522c65e5ecd0852c27d724c652189464f51cc, run 36308250793.
Полный R39.3: fae6209634712069ced5882fd933e5666006a8c2, run 36315038771.
CORE-SHA256SUMS.txt фиксирует три игровых файла. Их проверяют оба запуска.
PROVENANCE.json фиксирует SHA-256 и идентификаторы артефактов.
В evidence лежат неизменённые результаты предыдущего CI, а не новый прогон игры.
Статус упаковки не равен полной приёмке генерации.
'''


def main():
    out = Path('manual-kit')
    out.mkdir(exist_ok=False)
    sources = {
        'server.jar': find_exact('baseline', 'server.jar', EXPECTED['server.jar']),
        'world/datapacks/NeverNether.zip': find_exact('baseline', 'NeverNether.zip', EXPECTED['world/datapacks/NeverNether.zip']),
        'world/datapacks/NeverOverworld.zip': find_exact('r393', '*.zip', EXPECTED['world/datapacks/NeverOverworld.zip']),
    }
    for dest, source in sources.items():
        with zipfile.ZipFile(source) as z:
            if len(z.namelist()) != len(set(z.namelist())) or z.testzip() is not None:
                raise ValueError('Invalid input ZIP: ' + str(source))
        target = out / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != EXPECTED[dest]:
            raise ValueError('Copied file changed: ' + dest)
    # Independently check the two project fingerprint documents.
    with zipfile.ZipFile(out / 'world/datapacks/NeverOverworld.zip') as z:
        entries = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    fps = ('neveroverworld-worldgen-fingerprint.json', 'data/neverfolia/neveroverworld/worldgen_fingerprint.json')
    if entries[fps[0]] != entries[fps[1]]:
        raise ValueError('Unequal fingerprint documents')
    digest = hashlib.sha256()
    for name, data in sorted(entries.items()):
        if name in fps:
            continue
        raw = name.encode('utf-8')
        digest.update(len(raw).to_bytes(4, 'big')); digest.update(raw)
        digest.update(len(data).to_bytes(8, 'big')); digest.update(data)
    fp = json.loads(entries[fps[0]])
    if digest.hexdigest() != FP or fp['content_sha256'] != FP:
        raise ValueError('Content fingerprint mismatch')
    if fp['algorithm'] != 'sha256-path-and-content-v1' or fp['worldgen_id'] != 'NR-DEV-1':
        raise ValueError('Unsupported project fingerprint')
    # Require actual prior runtime evidence, not just a plausible pack filename.
    runtime = list(Path('runtime-evidence').rglob('r393-startup.json'))
    if len(runtime) != 1:
        raise ValueError('Missing exact prior runtime report')
    report = json.loads(runtime[0].read_text())
    expected_basename = {Path(k).name: v for k, v in EXPECTED.items()}
    if report.get('pass') is not True or report.get('inputs') != expected_basename:
        raise ValueError('Runtime report belongs to a different binary/pack set')
    if report.get('first', {}).get('pass') is not True or report.get('restart', {}).get('pass') is not True:
        raise ValueError('Prior start/restart was not successful')
    shutil.copytree('runtime-evidence', out / 'evidence/R39.3-prior-CI')
    write(out, 'CORE-SHA256SUMS.txt', ''.join(v + '  ' + k + '\n' for k, v in EXPECTED.items()))
    write(out, 'eula.txt', '# Read https://aka.ms/MinecraftEULA before accepting.\neula=false\n')
    write(out, 'jvm.args', '-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n')
    write(out, 'start.sh', LINUX, executable=True)
    write(out, 'start.ps1', WINDOWS)
    write(out, 'start.bat', '@echo off\r\ncd /d "%~dp0"\r\npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"\r\nset "RC=%ERRORLEVEL%"\r\necho.\r\necho Server or precheck finished with code %RC%.\r\npause\r\nexit /b %RC%\r\n')
    write(out, 'server.properties', '''level-name=world
level-seed=-4651369264513492755
initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip
server-ip=
server-port=25599
online-mode=true
enforce-secure-profile=true
white-list=true
enforce-whitelist=true
max-players=5
gamemode=creative
difficulty=normal
allow-flight=true
spawn-protection=0
view-distance=6
simulation-distance=4
pause-when-empty-seconds=-1
enable-rcon=false
enable-query=false
enable-status=true
motd=NeverFolia R39.3 Manual Generation Test
''')
    write(out, 'README-RU.md', README)
    write(out, 'BUG-REPORT-RU.md', '''# Результат ручного теста NeverFolia R39.3

Дата и время:
Версия клиента:
Java (вывод java -version):
Новая пустая папка и новый мир: да / нет
Seed: -4651369264513492755
Плагины: нет / список установленных дополнительно
Изменённые настройки:

## Баг
Тип: квадрат воды / пропавшая вода / основание под данжем / мобы / консоль / другое
Измерение:
Координаты X Y Z:
Название данжа, если известно:
Режим игрока и сложность:
Что ожидалось:
Что произошло:
Как повторить:
Сохраняется ли после команды stop и повторного запуска:
Время появления ошибки в logs/latest.log:
Приложения: скриншот с F3, logs/latest.log.
''')
    provenance = {
        'schema': 1, 'kit': 'NeverFolia-Test-R39.3-Complete',
        'packaging_commit': os.environ.get('GITHUB_SHA'), 'packaging_run': os.environ.get('GITHUB_RUN_ID'),
        'core_commit': 'c6e522c65e5ecd0852c27d724c652189464f51cc', 'core_run': 36308250793,
        'pack_commit': 'fae6209634712069ced5882fd933e5666006a8c2', 'pack_run': 36315038771,
        'source_artifact_ids': [10927954200, 10930701040, 10930681164],
        'files_sha256': EXPECTED, 'content_fingerprint': FP,
        'binary_bytes_modified': False, 'new_gameplay_test_performed': False,
        'production_accepted': False, 'known_missing_templates': 95,
        'eula_accepted': False, 'pregenerated_world_included': False,
    }
    write(out, 'PROVENANCE.json', json.dumps(provenance, indent=2) + '\n')
    subprocess.run(['bash', '-n', str(out / 'start.sh')], check=True)
    # EULA refusal must happen before Java starts. This is not a Minecraft run.
    refused = subprocess.run(['bash', 'start.sh'], cwd=out, capture_output=True, text=True)
    if refused.returncode != 1 or 'EULA_NOT_ACCEPTED' not in refused.stdout:
        raise ValueError('Linux EULA refusal check failed: ' + refused.stdout + refused.stderr)
    if list((out / 'world').rglob('level.dat')) or list((out / 'world').rglob('*.mca')):
        raise ValueError('Saved world must not be included')
    if sorted(p.name for p in (out / 'world/datapacks').iterdir()) != ['NeverNether.zip', 'NeverOverworld.zip']:
        raise ValueError('Unexpected additional datapack')
    write(out, 'PACKAGE-CHECK.json', json.dumps({
        'packaging_checks_pass': True, 'core_crc_and_hashes_checked': True,
        'project_fingerprint_checked': True, 'prior_runtime_inputs_matched': True,
        'bash_syntax_checked': True, 'bash_eula_refusal_checked': True,
        'minecraft_started_by_packager': False, 'gameplay_accepted': False,
    }, indent=2) + '\n')
    print(json.dumps({'result': 'PACKAGED', 'files_sha256': EXPECTED, 'folder': str(out),
                      'known_missing_templates': 95, 'production_accepted': False}, indent=2))

if __name__ == '__main__':
    main()
