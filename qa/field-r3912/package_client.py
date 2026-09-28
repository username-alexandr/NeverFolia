#!/usr/bin/env python3
"""Stage only validated own client binaries, not game libraries or server files."""
import hashlib,json,os,shutil
from pathlib import Path

def main():
    src=Path('client-output');dest=Path('client-delivery');dest.mkdir(exist_ok=False)
    build=json.loads((src/'build.json').read_text());runtime=json.loads((src/'registry-runtime.json').read_text())
    if not (build['compile_pass'] and runtime['pass'] and runtime['exit_code']==0):
        raise ValueError('Current build/registry test failed')
    if not (build['server_unchanged'] and build['datapack_unchanged']):
        raise ValueError('Server inputs were changed')
    allowed={'NeverLand-Enchantments-RU-26.2-R39.12.zip','NeverLand-Enchantment-UI-Fabric-26.2-R39.12.jar'}
    if set(build['output_sha256'])!=allowed: raise ValueError('Unexpected delivery files')
    for name,expected in build['output_sha256'].items():
        if hashlib.sha256((src/name).read_bytes()).hexdigest()!=expected: raise ValueError('Changed output '+name)
        shutil.copyfile(src/name,dest/name)
    readme='''# NeverLand R39.12 — клиентское отображение зачарований

Это НЕ новое серверное ядро. Оставьте свой сервер R39.11 и его мир без изменений.
Ничего из этого архива не помещать в server/plugins или world/datapacks.

## Без модов: русские названия

Поместите NeverLand-Enchantments-RU-26.2-R39.12.zip в resourcepacks используемого клиента Minecraft 26.2.
Внутренний ZIP не распаковывать. Включите его в Настройки → Наборы ресурсов, выше других пакетов,
которые задают названия Dungeons & Taverns. Выберите русский язык.
Swift Soar → «Стремительный полёт», Wither Coated → «Иссушающее покрытие».
Переведены остальные игровые названия; Bug Enchant подписан «Служебное зачарование».
В английской локали техническая запись получает пояснение Internal controller (not a survival enchantment).
Сам ресурс-пак НЕ скрывает книги. Он меняет только текст, не эффекты и не предметы.

## Fabric: дополнительно скрыть служебные книги

Нужен клиент Minecraft именно 26.2 с Fabric Loader 0.19.3 или новее и Java 25.
Поместите NeverLand-Enchantment-UI-Fabric-26.2-R39.12.jar в mods КЛИЕНТА.
Удалите только прежнюю версию neverland_enchantment_ui, если она уже установлена: две версии не нужны.
Отдельный Fabric API этому модулю не требуется. Перезапустите игру.
Мод включает те же переводы; отдельный ресурс-пак необязателен, но позволяет менять приоритет названий.

Фильтр работает при создании списков зачарованных книг в категориях creative и поиске.
Он исключает только технические контроллеры Nova; игровые кастомные и ванильные зачарования остаются.
Книги, уже находящиеся в инвентаре, не удаляются. Регистрации, эффекты, экипировка и лут не меняются.
Без Fabric используйте только ресурс-пак: служебные книги будут правильно подписаны, но останутся видимыми.

## Что действительно проверено

Собственные классы скомпилированы на Java 25. У официального клиента 26.2 сверены SHA-1, размер, версия
и оба адресуемых метода CreativeModeTabs: ровно один подходящий вызов HolderLookup.listElements в каждом.
На настоящем сервере с исходным NeverOverworld проверен тот же скомпилированный предикат:
16 служебных записей исключаются из отображения, 17 игровых и 2 контрольных ванильных сохраняются.
Все записи продолжают существовать в реестре. Это НЕ запуск графического клиента и НЕ применение Mixin.
Графический запуск, отображение названий в игре и совместимость с другими модами ещё проверяются вручную.
Сборка выполнена в GitHub Actions: локальный исполнитель чата возвращал ClientError. Доступ к ПК не использован.

## Ручная проверка и откат

Откройте ингредиенты и поиск книг. С Fabric служебные книги должны исчезнуть из списков, а игровые
Swift Soar и Wither Coated — остаться под русскими названиями. Уже выданные книги не должны исчезнуть.
При ошибке запуска уберите только новый клиентский JAR и сохраните logs/latest.log клиента.
Для отката перевода отключите ресурс-пак и мод. Сервер и мир откатывать не требуется.

## Не входит в этот этап

Нет изменений воды, льда, данжей, мобов, оставшихся шаблонов или способов получения зачарований.
Не заявляется исправление всех багов NeverFolia. В архиве нет server.jar, миров, QA-плагина или библиотек игры.
Точные контрольные суммы и границы проверки — REPORT.json, SHA256SUMS.txt.
'''
    (dest/'README-RU.md').write_text(readme,encoding='utf-8')
    report={'commit':os.environ.get('GITHUB_SHA'),'run':os.environ.get('GITHUB_RUN_ID'),'build':build,'registry_test':runtime,
            'scope':'Client-only addon. No server binary included or overwritten; client/Mixin launch remains manual.'}
    (dest/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (dest/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(dest.iterdir()) if p.is_file()))
    print('R3912_DELIVERY',json.dumps({'files':sorted(p.name for p in dest.iterdir()),'checks':len(runtime['fixture']['checks']),'hidden':runtime['fixture']['hidden_technical'],'server_replaced':False}))
if __name__=='__main__': main()
