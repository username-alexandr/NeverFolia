#!/usr/bin/env bash
# Isolated CI only: no production server files are modified.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p artifacts
SOURCE_SHA="$(git rev-parse HEAD)"
printf '%s\n' "$SOURCE_SHA" > artifacts/SOURCE-COMMIT.txt
python3 qa/field-r19/validate-external-structures-pack.py --self-test

set -euo pipefail
mkdir -p artifacts
git config --global user.email actions@github.com
git config --global user.name 'NeverFolia CI'
python3 scripts/prepare-never-nether-r13-upstream.py
test "$(git -C .work/Folia rev-parse HEAD)" = 14b7fee5c866fca9a40ede4a58998fb928140f65
bash scripts/apply-folia-patches-ci.sh .work/Folia
bash scripts/apply-neverfolia-post-patches.sh 2>&1 | tee artifacts/production-chain.log
for stage in 8 9 10 11 12 13 14; do
  python3 "scripts/apply-never-nether-experiment-r${stage}.py" .work/Folia --acknowledge-experimental-worldgen
done
python3 scripts/apply-never-nether-bug01-bounds.py .work/Folia
python3 scripts/apply-never-nether-experiment-r15.py .work/Folia --acknowledge-experimental-worldgen
python3 qa/ore-light-r12/defer-upper-pruning.py .work/Folia
python3 scripts/apply-never-overworld-fixpack-r22.py .work/Folia
python3 scripts/apply-never-nether-experiment-r16.py .work/Folia
python3 scripts/apply-never-overworld-fixpack-r22.py .work/Folia --check-only
python3 scripts/apply-never-nether-experiment-r16.py .work/Folia --check-only
(cd .work/Folia && ./gradlew :folia-server:createPaperclipJar --no-configuration-cache --stacktrace)
cp .work/Folia/folia-server/build/libs/folia-paperclip-*.jar artifacts/server.jar
cp .work/Folia/folia-server/build/libs/folia-bundler-*.jar artifacts/pack-input-bundler.jar || true

python3 qa/field-r37/test-materialized.py .work/Folia --output artifacts/r37-java-unit.json

set -euo pipefail
if [ ! -f artifacts/pack-input-bundler.jar ]; then
  python3 - <<'PY'
import shutil,zipfile
from pathlib import Path
found=[]
for p in Path('.work/Folia/folia-server/build/libs').glob('*.jar'):
    try:
        with zipfile.ZipFile(p) as z:
            if any(n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar') for n in z.namelist()):
                found.append(p)
    except zipfile.BadZipFile:
        pass
if len(found)!=1:
    raise SystemExit('pack-input bundler not uniquely found')
shutil.copyfile(found[0],'artifacts/pack-input-bundler.jar')
PY
fi
python3 scripts/build-never-overworld-core-pack.py --server-jar artifacts/pack-input-bundler.jar --output artifacts/NeverOverworld.zip
python3 scripts/build-never-overworld-native-structures.py --input artifacts/NeverOverworld.zip
python3 scripts/normalize-never-overworld-structure-type.py --input artifacts/NeverOverworld.zip
python3 scripts/build-never-overworld-external-structures-r19.py             --input artifacts/NeverOverworld.zip             --output artifacts/NeverOverworld-R19.zip
mv artifacts/NeverOverworld-R19.zip artifacts/NeverOverworld.zip
python3 scripts/fingerprint-never-overworld-pack.py --input artifacts/NeverOverworld.zip --inject
python3 scripts/fingerprint-never-overworld-pack.py --input artifacts/NeverOverworld.zip --verify

python3 scripts/build-never-nether-core-test1-pack.py --output .work/NeverNether-R13.zip
python3 scripts/fingerprint-never-nether-pack.py --input .work/NeverNether-R13.zip --inject
python3 scripts/build-never-nether-height-r14.py --input .work/NeverNether-R13.zip --output .work/NeverNether-R14.zip
python3 scripts/build-never-nether-field-r15.py --input .work/NeverNether-R14.zip --output .work/NeverNether-R15.zip
python3 scripts/fingerprint-never-nether-pack.py --input .work/NeverNether-R15.zip --verify
python3 scripts/build-never-nether-field-r16.py --input .work/NeverNether-R15.zip --output artifacts/NeverNether.zip
python3 scripts/fingerprint-never-nether-pack.py --input artifacts/NeverNether.zip --verify

python3 qa/field-r37/test-imports.py --sources .work/external-structures-r19 --output artifacts

set -euo pipefail
python3 qa/field-r19/audit-witch-source-nbt.py \
  --source .work/external-structures-r19/witch.zip \
  --merged artifacts/NeverOverworld.zip \
  --output artifacts/witch-source-nbt-qa.json

set -euo pipefail
python3 qa/field-r19/validate-external-structures-pack.py             --pack artifacts/NeverOverworld.zip             --spec worldgen-spec/never-overworld-external-structures-r19.json             --output artifacts/external-structures-pack-qa.json

cat > .work/r37-qa.init.gradle <<'GRADLE'
gradle.projectsEvaluated {
    def server = gradle.rootProject.project(':folia-server')
    def output = new File(gradle.rootProject.buildDir, 'r37-qa-classes')
    server.tasks.register('r37QaCompile', JavaCompile) {
        dependsOn server.tasks.named('classes')
        source server.files(new File(gradle.rootProject.projectDir, '../../qa/field-r37/R37DungeonQaPlugin.java'))
        destinationDirectory = output
        classpath = server.sourceSets.main.runtimeClasspath
        options.release = 25
    }
}
GRADLE
(cd .work/Folia && ./gradlew -I ../r37-qa.init.gradle :folia-server:r37QaCompile --no-configuration-cache --stacktrace)
jar --create --file artifacts/R37DungeonQa.jar -C .work/Folia/build/r37-qa-classes . -C qa/field-r37 plugin.yml
cp docs/FIELD-R37.md artifacts/READ-FIRST.md
(cd artifacts && sha256sum server.jar NeverOverworld.zip NeverNether.zip > SHA256SUMS.txt)
# Candidate inputs stay available if a later test fails. They are NOT promoted
# to a release by being uploaded.
touch artifacts/CANDIDATE-NOT-A-RELEASE.txt
python3 qa/field-r36/probe-water-square-seed.py \
    --jar artifacts/server.jar --overworld artifacts/NeverOverworld.zip \
    --nether artifacts/NeverNether.zip --qa-plugin artifacts/R37DungeonQa.jar \
    --source-sha "$SOURCE_SHA" --output artifacts
