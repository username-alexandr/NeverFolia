# NeverFolia TEST1 — установка

## Что входит в TEST1

- NeverFolia 26.2 development JAR на базе Folia 26.2.x / Java 25.
- `NeverOverworld-Core-NR-DEV-1-test1.zip` — тестовый профиль обычного мира.
- `NeverNether-Core-NN-DEV-1-test1.zip` — стабильный тестовый профиль Ада.
- End в TEST1 остаётся vanilla-compatible fallback. Контракт `NE-DEV-1` уже зарезервирован для будущего кастомного генератора NeverEnd.

## Важно

TEST1 предназначен только для нового тестового мира. Не запускайте его поверх production-мира без резервной копии.

Worldgen fingerprint lock защищает мир от случайного запуска с несовместимой версией Core-pack. Если содержимое worldgen pack изменилось, существующий тестовый мир может быть намеренно отклонён при старте.

## Требования

- Java 25.
- Новый каталог тестового сервера.
- Достаточно памяти для Folia; для первого одиночного теста рекомендуется не менее 4 ГБ RAM.

## Установка

1. Создайте новый пустой каталог сервера.
2. Положите туда JAR NeverFolia и запускайте именно его.
3. Первый раз запустите сервер для создания файлов, затем остановите его.
4. Примите EULA (`eula=true`).
5. Убедитесь, что `server.properties` содержит `level-name=world` или другое выбранное имя нового тестового мира.
6. Создайте `<level-name>/datapacks/`, если каталога ещё нет.
7. Поместите туда оба файла без распаковки:
   - `NeverOverworld-Core-NR-DEV-1-test1.zip`
   - `NeverNether-Core-NN-DEV-1-test1.zip`
8. Для нового мира укажите оба pack в `initial-enabled-packs`:

```properties
initial-enabled-packs=vanilla,file/NeverOverworld-Core-NR-DEV-1-test1.zip,file/NeverNether-Core-NN-DEV-1-test1.zip
```

9. Запустите сервер.

## Что должно получиться

### Overworld / NR-DEV-1

- высота мира: `Y=-512..511`;
- верхняя vanilla-совместимая генерация сохраняется;
- глубокая геология продолжается ниже обычного vanilla-дна;
- native lava-aquifer branch отключён;
- затопление `VANILLA_FLOODED` идёт до `Y=128` через Moonrise LIGHT barrier;
- закрытые глубокие пещеры не должны превращаться в сплошной океан;
- worldgen fingerprint создаётся отдельно от Nether.

### Nether / NN-DEV-1

- собственный NeverNether TEST1;
- расширенная высота и техническая roof-zone;
- исправленные chunk-owned Basalt Columns / ReplaceBlobs;
- строгая chunk-order determinism уже является обязательным CI gate;
- независимый NeverNether fingerprint lock.

### End / NE-DEV-1

- в этой версии кастомный NeverEnd ещё выключен;
- используется vanilla-compatible End;
- слот и контракт кастомного генератора уже зарезервированы, чтобы позже добавить NeverEnd без переделки общей архитектуры версий worldgen.

## Первые проверки в игре

Проверяйте только новый мир/новые чанки. Основные области проверки:

- Overworld: поверхность, береговая линия около уровня 128, глубокие пещеры, нижние уровни до -512, наличие/отсутствие случайной глубинной лавы.
- Nether: рельеф, Basalt Deltas, переходы чанков, верхняя и нижняя границы генерации.
- End: обычная vanilla-генерация без изменений.

При обнаружении ошибки сохраняйте координаты, seed и скриншот/лог — они позволяют воспроизвести worldgen детерминированно.
