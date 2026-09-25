"""Bounded, observable supervision of ONE disposable probe child process.

This reports liveness, not worldgen correctness. Only an advancing observation
count resets the no-progress deadline; log spam and repeated JSON do not. No
automatic retry, checkpoint migration, process lookup or unrelated PID killing.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

JVM_FLAGS = ['-Xms512M', '-Xmx3200M', '-XX:ActiveProcessorCount=4',
             '-Dpaper.disablePluginRemapping=true', '-Dneverfolia.qa.stageProbe=true']


def checked_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in ('JDK_JAVA_OPTIONS', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS'):
        if env.get(key):
            raise ValueError('External JVM injection is not permitted: ' + key)
    return env


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def report_status(path: Path, previous_count: int) -> dict:
    if not path.exists():
        if previous_count >= 0:
            raise ValueError('Probe report disappeared during the run')
        return {'stage': 'waiting_for_report', 'count': -1, 'phase': None, 'chunk': None}
    # The Java observer atomically replaces this JSON. A malformed current file
    # is not a transient partial write to silently ignore.
    with path.open(encoding='utf-8') as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or value.get('stage') not in ('running', 'completed', 'failed'):
        raise ValueError('Unknown or malformed probe report stage')
    rows = value.get('observations', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Malformed probe observation list')
    if len(rows) < previous_count:
        raise ValueError('Probe observation count moved backwards')
    last = rows[-1] if rows else {}
    return {'stage': value['stage'], 'count': len(rows), 'phase': last.get('phase'),
            'chunk': [last.get('x'), last.get('z')] if rows else None,
            'probe_error': value.get('error')}


def log_tail(path: Path, limit: int = 8192) -> str:
    try:
        with path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - limit))
            return stream.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''


def execute(command: list[str], directory: Path, timeout: float, *,
            env: dict[str, str] | None = None, heartbeat: float = 15,
            stall_timeout: float = 180, poll_interval: float = 1,
            stop_grace: float = 90, terminate_grace: float = 30,
            kill_grace: float = 10) -> dict:
    """Run and reap the child; caller adds immutable input verification evidence.

    Small timeout values are allowed here for subprocess tests. Public runner
    CLIs keep their stricter user-facing bounds. Heartbeats go to stderr, leaving
    stdout available for a single machine-readable result.
    """
    values = (timeout, heartbeat, stall_timeout, poll_interval,
              stop_grace, terminate_grace, kill_grace)
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Supervisor timeouts must be finite and positive')
    report = directory / 'plugins/NN-STAGE-R8-QA/report.json'
    log_path = directory / 'run.log'
    # The start runner creates a fresh directory; the resume runner archives old
    # evidence. Never count an already completed report as this child's result.
    if report.exists() or log_path.exists():
        raise ValueError('Old report/log exists; refusing to overwrite or reuse evidence')
    started = last_progress = time.monotonic()
    last_emit = -float('inf')
    current = {'stage': 'starting', 'count': -1, 'phase': None, 'chunk': None}
    result = {'stage': 'spawn_failed', 'process_exit_code': None, 'forced_stop': False,
              'release_ready': False}
    process = None
    count = -1

    def publish(stage: str, *, terminal: bool = False) -> None:
        nonlocal last_emit
        now = time.monotonic()
        status = {'schema': 1, 'kind': 'probe-liveness-not-acceptance',
                  'stage': stage, 'terminal': terminal,
                  'pid': process.pid if process is not None else None,
                  'observations': max(0, current['count']),
                  'phase': current.get('phase'), 'last_chunk': current.get('chunk'),
                  'elapsed_seconds': round(now - started, 3),
                  'no_progress_seconds': round(now - last_progress, 3),
                  'total_timeout_seconds': timeout, 'stall_timeout_seconds': stall_timeout,
                  'updated_unix_seconds': time.time(), 'release_ready': False,
                  'process_exit_code': process.returncode if process is not None else None,
                  'forced_stop': result['forced_stop'], 'worldgen_acceptance': 'not_evaluated'}
        write_json(directory / 'probe-progress.json', status)
        print(f"[NN-PROBE] stage={stage} observations={status['observations']} "
              f"phase={status['phase']} chunk={status['last_chunk']} "
              f"elapsed={status['elapsed_seconds']}s idle={status['no_progress_seconds']}s",
              file=sys.stderr, flush=True)
        last_emit = now

    try:
        publish('starting')
        with log_path.open('x', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.PIPE,
                                       stdout=log, stderr=subprocess.STDOUT, text=True)
            try:
                while True:
                    # A process that exited by itself is not accepted as a normal
                    # supervised stop, even if it happened to write "completed".
                    if process.poll() is not None:
                        result['stage'] = 'exited_early'
                        break
                    current = report_status(report, count)
                    now = time.monotonic()
                    if current['count'] > count:
                        count = current['count']
                        last_progress = now
                    if current['stage'] in ('completed', 'failed'):
                        result['stage'] = current['stage']
                        if current.get('probe_error'):
                            result['probe_error'] = str(current['probe_error'])
                        break
                    if now - started >= timeout:
                        result['stage'] = 'timeout'
                        break
                    if now - last_progress >= stall_timeout:
                        result['stage'] = 'startup_stalled' if count < 0 else 'stalled'
                        break
                    if now - last_emit >= heartbeat:
                        publish(current['stage'])
                    time.sleep(poll_interval)
            except KeyboardInterrupt:
                result['stage'] = 'interrupted'
            except (OSError, ValueError, TypeError) as error:
                result['stage'] = 'invalid_report' if isinstance(error, (ValueError, TypeError)) else 'monitor_error'
                result['error'] = f'{type(error).__name__}: {error}'
            finally:
                # Supervision errors must never skip shutdown of the child.
                try:
                    publish('stopping')
                finally:
                    if process.poll() is None:
                        try:
                            process.stdin.write('stop\n')
                            process.stdin.flush()
                            process.wait(timeout=stop_grace)
                        except (OSError, subprocess.TimeoutExpired):
                            result['forced_stop'] = True
                            if process.poll() is None:
                                process.terminate()
                            try:
                                process.wait(timeout=terminate_grace)
                            except subprocess.TimeoutExpired:
                                if process.poll() is None:
                                    process.kill()
                                try:
                                    process.wait(timeout=kill_grace)
                                except subprocess.TimeoutExpired:
                                    result['child_not_reaped'] = True
                                    result['stage'] = 'stop_failed'
                    if process.stdin is not None:
                        process.stdin.close()
    except OSError as error:
        result['stage'] = 'spawn_failed' if process is None else 'monitor_error'
        result['error'] = f'{type(error).__name__}: {error}'
    result['process_exit_code'] = process.returncode if process is not None else None
    result['elapsed_seconds'] = time.monotonic() - started
    result['last_observation_count'] = max(0, count)
    result['last_phase'] = current.get('phase')
    result['last_chunk'] = current.get('chunk')
    result['log_tail'] = log_tail(log_path)
    write_json(directory / 'probe-supervisor-result.json', result)
    publish(result['stage'], terminal=True)
    return result
