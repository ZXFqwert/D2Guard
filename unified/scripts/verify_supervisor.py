"""Real-process supervisor acceptance. Requires free ports 8765 and 5173."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from start_all import free_port, healthy_core, healthy_desk


def wait_for(check, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.2)
    raise AssertionError('Timed out waiting for expected process state')


def ports_free():
    try:
        for port in (8765, 5173):
            free_port(port)
        return True
    except RuntimeError:
        return False


def run():
    assert ports_free(), 'Stop the running app first; this test never kills unrelated processes.'
    command = [sys.executable, str(ROOT / 'start_all.py'), '--headless', '--no-build']
    results = []
    smoke = subprocess.run(command + ['--smoke-seconds', '2'], cwd=ROOT, capture_output=True,
                           encoding='utf-8', errors='replace', timeout=40)
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert smoke.stdout.index('CORE') < smoke.stdout.index('DESK')
    wait_for(ports_free)
    results.append('health ordering and normal shutdown: PASS')
    for failure in ('core_crash', 'supervisor_crash'):
        owner = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 encoding='utf-8', errors='replace')
        try:
            wait_for(lambda: healthy_core() and healthy_desk())
            conflict = subprocess.run(command, cwd=ROOT, capture_output=True,
                encoding='utf-8', errors='replace', timeout=10)
            assert conflict.returncode == 1 and 'occupied' in conflict.stderr
            assert healthy_core() and healthy_desk(), 'Conflict must preserve the running owner'
            if failure == 'core_crash':
                if os.name != 'nt':
                    raise RuntimeError('This process-failure probe currently targets Windows')
                # This port was verified free before launching our supervisor.
                lookup = subprocess.run(['pwsh', '-NoProfile', '-Command',
                    '(Get-NetTCPConnection -State Listen -LocalPort 8765).OwningProcess'],
                    capture_output=True, encoding='utf-8', errors='replace', check=True)
                core_pid = int(lookup.stdout.strip())
                os.kill(core_pid, 15)
                output, _ = owner.communicate(timeout=15)
                assert owner.returncode == 1, output
            else:
                owner.kill()
                owner.wait(timeout=10)
            wait_for(ports_free)
            results.append(f'port conflict preservation and {failure} peer cleanup: PASS')
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait(timeout=10)
    output = ROOT / 'output/supervisor-results.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n'.join(results))


if __name__ == '__main__':
    run()
