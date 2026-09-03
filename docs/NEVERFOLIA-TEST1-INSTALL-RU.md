# NeverFolia TEST1 — установка

## Что входит в TEST1

- NeverFolia `26.2-0.1.0-dev` development JAR на базе Folia 26.2.x / Java 25.
- `NeverOverworld-Core-NR-DEV-1-native-structures-v1.zip` — актуальный тестовый Core обычного мира.
- `NeverNether-Core-NN-DEV-1-test1.zip` — тестовый Core NeverNether.
- `NeverOverworld-geology-audit.json` — CI-отчёт по фактически сохранённым глубоким рудам для той же сборки.
- `SHA256SUMS.txt` — контрольные суммы JAR/Core-pack/геологического отчёта.
- End в TEST1 остаётся vanilla-compatible fallback. Контракт `NE-DEV-1` уже зарезервирован для будущего кастомного генератора NeverEnd.

## Важно

TEST1 предназначен только для нового тестового мира. Не запускайте его поверх production-мира без резервной копии.

Worldgen fingerprint lock защищает мир от случайного запуска с несовместимой версией Core-pack. Если содержимое worldgen pack изменилось, существующий тестовый мир может быть намеренно отклонён при старте.

Для проверки правок генерации используйте только новые чанки или полностью новый тестовый мир. Уже сохранённые чанки автоматически не перегенерируются.

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
   - `NeverOverworld-Core-NR-DEV-1-native-structures-v1.zip`;
   - `NeverNether-Core-NN-DEV-1-test1.zip`.
8. Для нового мира укажите оба pack в `initial-enabled-packs`:

```properties
initial-enabled-packs=vanilla,file/NeverOverworld-Core-NR-DEV-1-native-structures-v1.zip,file/NeverNether-Core-NN-DEV-1-test1.zip
```

9. Запустите сервер.
10. После первого успешного старта сохраните `logs/latest.log` до начала тестирования — в нём должны быть маркеры активации NeverOverworld/NeverNether и worldgen fingerprint.

## Что должно получиться

### Overworld / NR-DEV-1

- высота мира: `Y=-512..511`;
- верхняя vanilla-совместимая генерация сохраняется;
- глубокая геология продолжается ниже обычного vanilla-дна;
- native lava-aquifer branch отключён;
- затопление `VANILLA_FLOODED` идёт до `Y=128` через Moonrise LIGHT barrier;
- закрытые глубокие пещеры не должны превращаться в сплошной океан;
- native deep geology генерирует coal/iron/copper/gold/redstone/lapis/diamond/emerald;
- для stone используется обычная версия руды, для deepslate/tuff — deepslate-версия;
- diamond balance v2 работает в диапазоне примерно `Y=-496..-160`;
- emerald balance v2 работает в диапазоне примерно `Y=-384..-96`;
- worldgen fingerprint создаётся отдельно от Nether.

### Нативные структуры Overworld

В TEST1 включены восемь NeverFolia-структур:

- `neverfolia:buried_sanctum`;
- `neverfolia:abyssal_archive`;
- `neverfolia:ancient_cistern`;
- `neverfolia:collapsed_mine`;
- `neverfolia:geode_vault`;
- `neverfolia:flooded_ruins`;
- `neverfolia:prospector_camp`;
- `neverfolia:sealed_cache`.

Обычный `/locate structure neverfolia:<id>` для этих структур использует predictive no-generation fast locate: поиск не должен генерировать сотни чанков и подвешивать сервер. После перехода к найденной области структура должна иметь реальный Minecraft structure start.

### Nether / NN-DEV-1

- собственный NeverNether TEST1, а не vanilla Nether;
- расширенная высота и техническая roof-zone;
- исправленные chunk-owned Basalt Columns / ReplaceBlobs;
- строгая chunk-order determinism является обязательным CI gate;
- независимый NeverNether fingerprint lock.

### End / NE-DEV-1

- в этой версии кастомный NeverEnd ещё выключен;
- используется vanilla-compatible End;
- слот и контракт кастомного генератора уже зарезервированы, чтобы позже добавить NeverEnd без переделки общей архитектуры версий worldgen.

## Первые проверки в игре

Проверяйте только новый мир/новые чанки.

### 1. Overworld — поверхность и затопление

- пройдите несколько разных биомов;
- проверьте береговую линию около `Y=128`;
- убедитесь, что открытые низины затопляются;
- убедитесь, что закрытые пещеры не заполнены водой целиком;
- проверьте отсутствие случайных глубинных лавовых карманов, которые должны были быть удалены native aquifer policy.

### 2. Overworld — глубокая геология и руды

Проверяйте несколько удалённых областей, а не один чанк.

- `Y=-100..-160`: переход к глубокой геологии, coal/iron/copper и верхняя граница emerald;
- `Y=-160..-300`: redstone/lapis/gold/diamond/emerald;
- `Y=-300..-400`: diamond, emerald, iron, redstone и глубокие геологические провинции;
- `Y=-400..-496`: наиболее глубокие diamond/iron/redstone/gold-провинции;
- около `Y=-512`: корректный нижний envelope/bedrock без выхода за границу мира.

Если руда находится в deepslate/tuff, ожидается именно `deepslate_*_ore`. В каменной породе ожидается обычный `*_ore`.

### 3. Overworld — структуры и locate

Проверить минимум:

```text
/locate structure neverfolia:prospector_camp
/locate structure neverfolia:collapsed_mine
/locate structure neverfolia:buried_sanctum
```

Команда должна отвечать без watchdog-зависания. После телепорта/подхода к координатам проверьте фактическое наличие структуры и сохраните координаты при несовпадении.

### 4. Nether

Проверьте:

- рельеф NeverNether;
- Basalt Deltas;
- переходы между чанками;
- нижнюю границу;
- основную область генерации;
- верхнюю техническую roof-zone;
- отсутствие визуальных разрывов, зависящих от порядка загрузки чанков.

### 5. End

В TEST1 ожидается обычная vanilla-compatible генерация без кастомного NeverEnd.

## Что присылать при обнаружении ошибки

Для воспроизводимого worldgen-багрепорта сохраняйте:

- точную версию/имя JAR;
- SHA-256 или приложенный `SHA256SUMS.txt`;
- seed мира;
- dimension;
- координаты `X Y Z` и chunk `X Z`;
- команду, которой ошибка воспроизводится;
- `logs/latest.log`;
- скриншот, если проблема визуальная;
- указание, был ли чанк новым или уже существовал до замены сборки.

Это позволяет воспроизвести NeverFolia worldgen детерминированно и сравнить тот же чанк в обратном порядке генерации.
