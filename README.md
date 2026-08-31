# NeverFolia

Private NeverLand server core based on Folia 26.2.x.

## Current status

Architecture and bootstrap phase. NeverFolia is developed as a Folia-native core with custom NeverLand world generation, deterministic worldgen, dimension lifecycle management, diagnostics, pregeneration, and compatibility tooling.

## Build policy

- Java 25
- Upstream base: PaperMC/Folia `ver/26.2.x`
- Development builds are tested outside production worlds.
- Production receives only staging-tested releases.
- Worldgen versions are independent from NeverFolia JAR versions.

GitHub Actions will build and publish JAR artifacts automatically once the Gradle/Folia source tree is present in this repository.
