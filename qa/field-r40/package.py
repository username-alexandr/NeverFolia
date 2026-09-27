#!/usr/bin/env python3
"""Package a clearly labelled manual-test kit only after current R40 evidence.
No saved world, test plugin, client mod or user EULA acceptance is copied.
"""
from pathlib import Path
import hashlib,json,os,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'manual-test'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    result=json.loads((ROOT/'artifacts/runtime.json').read_text());build=result['build']
    if result.get('bounded_integration_pass') is not True or result.get('global_closure_proven') is not False:raise ValueError('No accepted bounded integration evidence')
    OUT.mkdir(exist_ok=False);packs=OUT/'world/datapacks';packs.mkdir(parents=True)
    files=[('server.jar',OUT/'server.jar',build['candidate_core_sha256']),('NeverOverworld.zip',packs/'NeverOverworld.zip',build['pack_sha256']),('NeverNether.zip',packs/'NeverNether.zip',build['nether_sha256'])]
    for name,dest,expected in files:
        source=ROOT/'candidate'/name
        if sha(source)!=expected:raise ValueError('Changed compiled input '+name)
        shutil.copyfile(source,dest)
        if sha(dest)!=expected:raise ValueError('Invalid copied file '+name)
    for name in ('build.json','summary.json','runtime.json','provenance.json'):
        shutil.copyfile(ROOT/'artifacts'/name,OUT/name)
    (OUT/'eula.txt').write_text('eula=false\n')
    (OUT/'jvm.args').write_text('-Xms1G\n-Xmx4G\n-Dfile.encoding=UTF-8\n-Dneverfolia.r395OceanClosure=true\n')
    (OUT/'server.properties').write_text('level-name=world\nlevel-seed=-4651369264513492755\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25610\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nmax-players=2\ngamemode=creative\ndifficulty=normal\nallow-flight=true\nview-distance=6\nsimulation-distance=3\npause-when-empty-seconds=-1\nenable-rcon=false\n')
    (OUT/'start.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "$0")"\njava -version\nsha256sum -c BINARIES.sha256\nexec java @jvm.args -jar server.jar --nogui\n')
    (OUT/'start.bat').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\njava -version\r\njava "@jvm.args" -jar server.jar --nogui\r\npause\r\n')
    (OUT/'README-RU.md').write_text('''# NeverFolia R40 — объединённый тест океанской заливки

Состав: точное ядро R39.9 с сохранёнными правками снега R39.6 и защиты шахт R39.9,
новый LIGHT-вызов ограниченной заливки R40 и прежние два согласованных датапака.
Клиентского мода и QA-плагинов здесь нет. Сборка инкрементальная Java 25, не полный Gradle.

## Что изменено
Заливка ищет трёхмерный путь от открытой поверхности океана до воздуха, в том числе
сбоку под навес острова. Пишет только в текущий новый чанк. Камень, существующие
состояния воды, лёд, лава и блоки построек не заменяются этим проходом. Защита шахт
строится из сохранённых границ; закрытые полости не получают воду без доказанного пути.
Размер области доказательства — 3×3 чанка. Открытая полость с выходом дальше области
может остаться сухой. Это не решение всех воздушных карманов, не исправление льда
и не защита любого помещения: открытая в океан комната без собственной защиты может
быть затоплена. Все варианты данжей не приняты. 95 старых ресурсных пробелов не исправлялись.

## Что реально проверено
Синтетическая сцена на настоящем серверном чанке: боковой вход под крышей, закрытая
пещера, записанная сухая шахта без временного кэша, лава, лёд, текущая вода и неизвестные
соседи. Затем отдельные реальные новые миры: исходный R39.9, повтор, обратный порядок,
кандидат с выключенным проходом, включённый кандидат, его перезапуск и обратный порядок.
В каждой фазе те же 54 чанка в шести районах, не весь мир. Сохранённые состояния
сравниваются поблочно. Для каждого целевого включённого прохода отдельный Python BFS
проверяет фактический сохранённый вход Java и точный набор записанных клеток.
Числа текущего прогона — в summary.json и runtime.json, не в рекламном описании.

Полное совпадение прямого и обратного порядка — отдельный показатель
strict_generation_order_equal. Его отрицательный результат не скрывается: исходная
генерация также зависит от порядка. Этот архив выдан по ограниченной проверке
интеграции/безопасности, НЕ по общей приёмке генерации. production_accepted=false.

## Запуск
1. Распаковать ТОЛЬКО в новую пустую папку. Прежний мир со скриншотами не удалять.
2. Установить Java 25 отдельно. Прочитать Minecraft EULA; при согласии вручную
   изменить eula=false на eula=true. Сборщик не принимает соглашение за пользователя.
3. Windows: start.bat. Linux: bash start.sh. Альтернатива из каталога:
   java "@jvm.args" -jar server.jar --nogui
4. Подключение с этой же машины: localhost:25610. Для удалённой тестовой машины
   использовать SSH-туннель; адрес/firewall без необходимости не открывать в интернет.
5. После Done в консоли: whitelist add ВАШ_НИК, затем отдельно op ВАШ_НИК.
6. Штатная остановка: stop. Не закрывать окно во время записи мира.

В jvm.args проход включён флагом -Dneverfolia.r395OceanClosure=true. Историческое имя
сохранено для совместимости тестов; фактически вызывается класс R40. Без флага
эксперимент выключен. Не запускать через старый launcher без jvm.args.
Экспорт тяжёлых диагностических witness-файлов для ручного теста выключен.
Linux launcher проверяет три хеша. Windows launcher только запускает Java;
проверка server.jar вручную: PowerShell Get-FileHash .\\server.jar -Algorithm SHA256.
BINARIES.sha256 содержит ожидаемые хеши. SHA256SUMS.txt относится к исходной распаковке
до редактирования eula.txt и настроек.

## Короткий ручной тест
Сначала /seed: ожидается -4651369264513492755.
/gamemode spectator
/tp @s 106 62 32
/tp @s -3041 63 -3455
/tp @s -27159 66 -12292
Это точки камеры со старых скриншотов, не точные адреса повреждённых блоков.
Искать оставшиеся водяные стены у островов. Не исправлять воду блоками или вёдрами.
При повторении — F3, координаты дефекта, общий и ближний ракурс, logs/latest.log.
После stop и запуска того же мира проверить то же место. Старые сохранения этот
проход не переписывает. Повторно обходить все данжи не требуется.
''',encoding='utf-8')
    (OUT/'BINARIES.sha256').write_text(''.join(sha(path)+'  '+path.relative_to(OUT).as_posix()+'\n' for _,path,_ in files))
    (OUT/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(OUT).as_posix()+'\n' for p in sorted(OUT.rglob('*')) if p.is_file()))
    print('R40_MANUAL_KIT_READY',build['candidate_core_sha256'])
if __name__=='__main__':main()
