# Isolated R6 entity-ownership QA

Never install this plugin on a live or persistent user world. It creates temporary
entities on the Nether owning region, invokes finite D&T actions, then discards
only the entities it created and records `plugins/NN-DNT-R6-QA/result.json`.

Compile with Java 25 against the exact full R6 runtime classpath:

```sh
javac -cp "$R6_CLASSPATH" -d /temporary/qa-classes qa/nevernether-r6/NeverNetherDntQaPlugin.java
cp qa/nevernether-r6/plugin.yml /temporary/qa-classes/plugin.yml
jar --create --file /isolated/server/plugins/NN-DNT-R6-QA.jar -C /temporary/qa-classes .
```

Start a new loopback-only NeverFolia test server with the complete matching Nether
pack. Wait for the QA result, stop normally, and run the startup content validator.
A stale result from an earlier invocation is not evidence for a later run.

The assertions use real entities and an actual Folia RegionScheduler task, not a
fake TickThread. Projectile identity is captured by its accepted launch event;
an immediate world query is not assumed to see a just-spawned entity.

The 50 checks do not prove all gameplay, every structure's natural placement,
region-boundary owner-removal semantics, or chunk-order determinism.
