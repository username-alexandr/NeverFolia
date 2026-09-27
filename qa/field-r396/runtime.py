#!/usr/bin/env python3
"""Isolated loopback baseline/fix fixtures plus candidate restart.
Never changes a user world or accepts the Minecraft EULA for a user installation.
Uses the repository's existing ephemeral CI test-world convention.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, threading, time
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts'
WORK = ROOT / '.work/r396-runtime'
SEED = -4651369264513492755
BAD = ('Failed to load registries', 'Failed to load datapacks', 'Overworld settings missing', 'Unknown registry key', 'Block-attached entity at invalid position', '[ChunkTaskScheduler] Chunk system error', 'Exception in server tick loop')


def need(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def phase(name, jar, folder, fixed, with_fixture):
    result = {'pass': False}
    log_path = OUT / (name + '.log')
    proc = None
    reader = None
    lines = []
    try:
        proc = subprocess.Popen(['java', '-XX:ActiveProcessorCount=4', '-Xms512M', '-Xmx3G', '-Dneverfolia.qaExpectFixedRemoval=' + str(fixed).lower(), '-jar', str(jar), '--nogui'], cwd=folder, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        def pump():
            with log_path.open('w') as stream:
                for line in proc.stdout:
                    lines.append(line)
                    stream.write(line)
                    stream.flush()
        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        def wait_for(tokens, seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                for line in list(lines):
                    if any(token in line for token in tokens): return line.rstrip()
                if proc.poll() is not None: raise RuntimeError('Server exited before event: ' + repr(tokens))
                time.sleep(0.2)
            raise TimeoutError('No server event: ' + repr(tokens))
        result['done'] = wait_for(['Done ('], 300)
        if with_fixture:
            result['marker'] = wait_for(['R396 REMOVAL QA PASS', 'R396 REMOVAL QA FAIL'], 100)
            fixture = json.loads((folder / 'plugins/R396RemovalQa/result.json').read_text())
            (OUT / (name + '-fixture.json')).write_text(json.dumps(fixture, indent=2) + '\n')
            result['fixture'] = fixture
            need(fixture.get('pass') is True and fixture.get('expect_fixed') is fixed, 'Fixture failed or wrong version expected')
            need(len(fixture.get('cases', [])) == 10 and all(c.get('pass') is True for c in fixture['cases']), 'Incomplete fixture coverage')
        proc.stdin.write('stop\n')
        proc.stdin.flush()
        result['exit_code'] = proc.wait(timeout=100)
        reader.join(timeout=10)
        need(not reader.is_alive(), 'Log reader not complete')
        result['targeted_errors'] = [line.rstrip() for line in lines if any(token in line for token in BAD)]
        need(result['exit_code'] == 0, 'Not a clean server stop')
        need(not result['targeted_errors'], 'Targeted runtime errors')
        result['pass'] = True
    except Exception as error:
        result['error'] = repr(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write('stop\n'); proc.stdin.flush(); proc.wait(timeout=30)
            except Exception:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=10)
        if reader is not None: reader.join(timeout=10)
        (OUT / (name + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(name, json.dumps({k: v for k, v in result.items() if k in ('pass', 'exit_code', 'error')}), flush=True)
    return result


def main():
    WORK.mkdir(parents=True, exist_ok=False)
    build = json.loads((OUT / 'build.json').read_text())
    baseline = ROOT / 'baseline/server.jar'
    candidate = ROOT / 'candidate/server.jar'
    need(sha(baseline) == build['base_core_sha256'], 'Wrong baseline JAR')
    need(sha(candidate) == build['candidate_core_sha256'], 'Wrong candidate JAR')
    version = subprocess.run(['java', '-version'], text=True, capture_output=True, check=True)
    need('version "25' in version.stderr + version.stdout, 'Java 25 required')
    report = {'pass': False, 'scope': '10 synthetic real-chunk fixtures on each kernel and candidate startup/restart. Not natural generation, full removal chain, dry-mine geometry or visual water-wall acceptance.', 'seed': str(SEED), 'java': version.stderr + version.stdout, 'build': build, 'production_accepted': False}
    def prepare(name):
        folder = WORK / name
        packs = folder / 'world/datapacks'
        packs.mkdir(parents=True, exist_ok=False)
        for filename in ('NeverOverworld.zip', 'NeverNether.zip'):
            shutil.copyfile(ROOT / 'candidate' / filename, packs / filename)
        (folder / 'plugins').mkdir()
        shutil.copyfile(ROOT / '.work/r396-build/R396RemovalQa.jar', folder / 'plugins/R396RemovalQa.jar')
        (folder / 'eula.txt').write_text('eula=true\n')
        (folder / 'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\ninitial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\nserver-ip=127.0.0.1\nserver-port=25601\nonline-mode=true\nenforce-secure-profile=true\nview-distance=2\nsimulation-distance=2\nmax-players=1\nenable-rcon=false\nenable-query=false\nenable-status=false\npause-when-empty-seconds=-1\n')
        return folder
    try:
        base_folder = prepare('baseline')
        fixed_folder = prepare('candidate')
        report['baseline'] = phase('r396-baseline', baseline, base_folder, False, True)
        report['candidate'] = phase('r396-candidate', candidate, fixed_folder, True, True)
        if report['candidate']['pass']:
            plugin = fixed_folder / 'plugins/R396RemovalQa.jar'
            plugin.rename(plugin.with_suffix('.disabled'))
            report['restart'] = phase('r396-restart', candidate, fixed_folder, True, False)
        else:
            report['restart'] = {'pass': False, 'reason': 'Candidate fixture failed'}
        left = report['baseline'].get('fixture', {}).get('cases', [])
        right = report['candidate'].get('fixture', {}).get('cases', [])
        if len(left) == len(right) == 10:
            need([r['name'] for r in left] == [r['name'] for r in right], 'Different fixture sets')
            delta = [a['name'] for a, b in zip(left, right) if a['actual'] != b['actual']]
            report['changed_fixture_results'] = delta
            need(delta == ['topmost_snow_with_water_contact'], 'Unexpected runtime behavior delta: ' + repr(delta))
            need(left[0]['sampled_floor'] == right[0]['sampled_floor'] == 64, 'Heightmap equality not actually reproduced')
        report['inputs_unchanged'] = sha(baseline) == build['base_core_sha256'] and sha(candidate) == build['candidate_core_sha256']
        for folder in (base_folder, fixed_folder):
            for filename, field in (('NeverOverworld.zip', 'pack_sha256'), ('NeverNether.zip', 'nether_sha256')):
                report['inputs_unchanged'] &= sha(folder / 'world/datapacks' / filename) == build[field]
        report['pass'] = all(report[k]['pass'] for k in ('baseline', 'candidate', 'restart')) and report['inputs_unchanged'] and report.get('changed_fixture_results') == ['topmost_snow_with_water_contact']
    except Exception as error:
        report['error'] = repr(error)
    finally:
        (OUT / 'runtime.json').write_text(json.dumps(report, indent=2) + '\n')
    need(report['pass'], 'R396 bounded acceptance failed; see retained evidence')

if __name__ == '__main__': main()
