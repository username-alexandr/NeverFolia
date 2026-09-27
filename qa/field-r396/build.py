#!/usr/bin/env python3
"""One-class incremental build from exact R38, not a full Gradle build.
No experimental R395 closure or client mod is installed by this script.
"""
from pathlib import Path
import hashlib, importlib.util, io, json, os, shutil, subprocess, zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts'
WORK = ROOT / '.work/r396-build'
CAND = ROOT / 'candidate'
BASE = '411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32'
PACK = 'a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be'
NETHER = '5e47f953cadbd5451b04d1682642417c9a40c726cf06e935c02cecdcb5eb2a10'
CLASS = 'net/minecraft/world/level/chunk/NeverOverworldWaterPolicyR38.class'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def find(folder, pattern, expected):
    values = [p for p in Path(folder).rglob(pattern) if p.is_file() and sha(p) == expected]
    need(len(values) == 1, 'Missing/ambiguous exact artifact: ' + pattern)
    return values[0]


def run(args, name):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    (OUT / name).write_text(result.stdout)
    print(result.stdout, flush=True)
    need(result.returncode == 0, 'Failed: ' + name)
    return result.stdout


def zip_members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        need(len(names) == len(set(names)), 'Duplicate ZIP paths')
        need(z.testzip() is None, 'ZIP CRC failure')
        return {n: z.read(n) for n in names}


def main():
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=False)
    CAND.mkdir(exist_ok=False)
    libs = WORK / 'libs'
    libs.mkdir()
    base = find(ROOT / 'baseline', 'server.jar', BASE)
    pack = find(ROOT / 'r393', '*.zip', PACK)
    nether = find(ROOT / 'baseline', 'NeverNether.zip', NETHER)
    base_raw = base.read_bytes()
    outer = zip_members(base_raw)
    nested = [n for n in outer if n.startswith('META-INF/versions/') and n.endswith('/folia-26.2.jar')]
    need(len(nested) == 1, 'Wrong bundled server count')
    nested = nested[0]
    inner_raw = outer[nested]
    inner = zip_members(inner_raw)
    need(CLASS in inner, 'Baseline policy missing')
    for index, (name, payload) in enumerate(outer.items()):
        if name.endswith('.jar') and name.startswith(('META-INF/libraries/', 'META-INF/versions/')):
            (libs / (str(index) + '-' + Path(name).name)).write_bytes(payload)
    providers = []
    for path in libs.glob('*.jar'):
        with zipfile.ZipFile(path) as z:
            if 'org/bukkit/Bukkit.class' in z.namelist():
                providers.append(path)
    with zipfile.ZipFile(ROOT / 'debug/diagnostics.zip') as z:
        if not providers:
            options = []
            for name in z.namelist():
                if 'folia-api' in name and name.endswith('.jar'):
                    raw = z.read(name)
                    with zipfile.ZipFile(io.BytesIO(raw)) as api:
                        if 'org/bukkit/Bukkit.class' in api.namelist():
                            options.append(raw)
            need(len(options) == 1, 'Exact API provider unavailable')
            path = libs / 'folia-api.jar'
            path.write_bytes(options[0])
            providers.append(path)
        engine_sources = OUT / 'actual-engine-source'
        engine_sources.mkdir()
        for basename in ('Heightmap.java', 'ChunkAccess.java', 'NeverOverworldWaterPolicyR38.java', 'NeverOverworldSnowBlockCleanupR19.java'):
            matches = [n for n in z.namelist() if n.endswith('/' + basename)]
            for index, name in enumerate(matches):
                (engine_sources / (str(index) + '-' + basename)).write_bytes(z.read(name))
    need(len(providers) == 1, 'Ambiguous Bukkit API')
    cp = os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    classes = WORK / 'classes'
    tests = WORK / 'tests'
    plugin_classes = WORK / 'plugin-classes'
    for directory in (classes, tests, plugin_classes):
        directory.mkdir()
    source = ROOT / 'native/overworld-r38/NeverOverworldWaterPolicyR38.java'
    need(source.read_text().count('waterContact && floor < 128 && y >= floor && y <= 128') == 1, 'Unexpected policy')
    run(['javac', '--release', '25', '-proc:none', '-cp', cp, '-d', str(classes), str(source)], 'policy-javac.log')
    replacements = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob('*.class')}
    need(set(replacements) == {CLASS}, 'Unexpected compiled classes')
    need(int.from_bytes(replacements[CLASS][6:8], 'big') == 69, 'Wrong Java class version')
    primitive = WORK / 'PolicyBoundaryTest.java'
    primitive.write_text('''import net.minecraft.world.level.chunk.NeverOverworldWaterPolicyR38;
public final class PolicyBoundaryTest {
 public static void main(String[] args) {
  boolean fixed = Boolean.parseBoolean(args[0]); long checks=0, differences=0;
  for (int y=-512;y<=129;y++) for(int floor=-512;floor<=129;floor++) for(boolean contact:new boolean[]{false,true}) {
   boolean old=contact && floor<128 && y>floor && y<=128;
   boolean expected=contact && floor<128 && y>=floor && y<=128;
   boolean actual=NeverOverworldWaterPolicyR38.allowsNewWater(y,floor,contact);
   if(actual!=(fixed?expected:old))throw new AssertionError(y+"/"+floor+"/"+contact);
   if(expected!=old) { if(!(contact && y==floor && floor<128))throw new AssertionError("overbroad delta"); differences++; }
   checks++;
  }
  if(differences!=640)throw new AssertionError("wrong bounded delta: "+differences);
  System.out.println("POLICY_BOUNDARY_PASS fixed="+fixed+" comparisons="+checks+" changed_cases="+differences);
 }
}
''')
    run(['javac', '--release', '25', '-proc:none', '-cp', cp, '-d', str(tests), str(primitive)], 'boundary-javac.log')
    run(['java', '-cp', str(tests) + os.pathsep + cp, 'PolicyBoundaryTest', 'false'], 'baseline-boundary.log')
    run(['java', '-cp', str(tests) + os.pathsep + str(classes) + os.pathsep + cp, 'PolicyBoundaryTest', 'true'], 'candidate-boundary.log')
    run(['javac', '--release', '25', '-proc:none', '-cp', str(classes) + os.pathsep + cp, '-d', str(plugin_classes), str(ROOT / 'qa/field-r396/R396RemovalQa.java')], 'plugin-javac.log')
    with zipfile.ZipFile(WORK / 'R396RemovalQa.jar', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in plugin_classes.rglob('*.class'):
            z.write(p, p.relative_to(plugin_classes).as_posix())
        z.writestr('plugin.yml', 'name: R396RemovalQa\nversion: 1\nmain: R396RemovalQa\napi-version: \'26.2\'\nfolia-supported: true\n')
    module_path = ROOT / 'qa/field-r395/jar_packaging.py'
    spec = importlib.util.spec_from_file_location('r396_zip', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run(['python3', str(module_path)], 'jar-packaging-tests.log')
    patched_inner = module.rewrite_zip(inner_raw, replacements)
    versions = []
    changed_rows = 0
    for line in outer['META-INF/versions.list'].decode().splitlines():
        fields = line.split('\t')
        need(len(fields) == 3, 'Unexpected versions manifest')
        if 'META-INF/versions/' + fields[2] == nested:
            need(fields[0] == digest(inner_raw), 'Invalid baseline bundled checksum')
            fields[0] = digest(patched_inner)
            changed_rows += 1
        versions.append('\t'.join(fields))
    need(changed_rows == 1, 'No unique versions row')
    patched_outer = module.rewrite_zip(base_raw, {nested: patched_inner, 'META-INF/versions.list': ('\n'.join(versions) + '\n').encode()})
    new_inner = zip_members(patched_inner)
    new_outer = zip_members(patched_outer)
    need(set(inner) == set(new_inner), 'Changed bundled membership')
    need(set(outer) == set(new_outer), 'Changed outer membership')
    need({n for n in inner if inner[n] != new_inner[n]} == {CLASS}, 'Unexpected modified bundled entry')
    need({n for n in outer if outer[n] != new_outer[n]} == {nested, 'META-INF/versions.list'}, 'Unexpected modified outer entry')
    (CAND / 'server.jar').write_bytes(patched_outer)
    shutil.copyfile(pack, CAND / 'NeverOverworld.zip')
    shutil.copyfile(nether, CAND / 'NeverNether.zip')
    report = {'build_pass': True, 'kind': 'incremental single-class javac --release 25; NOT full Gradle', 'base_core_sha256': BASE, 'candidate_core_sha256': sha(CAND / 'server.jar'), 'pack_sha256': PACK, 'nether_sha256': NETHER, 'changed_bundled_entries': [CLASS], 'preserved_bundled_entries': len(inner)-1, 'policy_source_sha256': sha(source), 'runtime_tested': False, 'production_accepted': False, 'experimental_ocean_closure_installed': False}
    (OUT / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    (WORK / 'classpath.txt').write_text(cp)
    print(json.dumps(report, indent=2), flush=True)

if __name__ == '__main__':
    main()
