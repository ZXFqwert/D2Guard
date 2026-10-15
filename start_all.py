"""D2Guard supervisor: localhost only, verified readiness, owned-child cleanup."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
CORE, DESK = ROOT / 'D2guard_core', ROOT / 'D2guard_desk'


class ChildJob:
    """Windows kills the entire owned tree even if the supervisor is terminated."""
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, process):
        if self.handle and not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            import ctypes
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def free_port(port):
    with socket.socket() as sock:
        if os.name == 'nt':
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as exc:
            raise RuntimeError(f'127.0.0.1:{port} is occupied. Stop its owner before starting; no existing process was killed.') from exc


def healthy_core():
    try:
        with urlopen('http://127.0.0.1:8765/openapi.json', timeout=2) as response:
            schema = json.load(response)
        expected = json.loads((ROOT / 'D2guard_contract.json').read_text(encoding='utf-8-sig'))
        return schema['info']['title'] == 'd2guard_core' and all(
            e['method'].lower() in schema['paths'].get(e['path'], {}) for e in expected['endpoints'].values())
    except (OSError, ValueError, KeyError):
        return False


def healthy_desk():
    try:
        with urlopen('http://127.0.0.1:5173', timeout=2) as response:
            return b'<div id="root"' in response.read()
    except OSError:
        return False


def wait_ready(process, check, name):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{name} exited with {process.returncode}; see output/logs')
        if check():
            print(f'{name} READY', flush=True)
            return
        time.sleep(.2)
    raise RuntimeError(f'{name} readiness timeout; see output/logs')


def stop_owned(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       encoding='utf-8', errors='replace', check=False)
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def prepare(no_build):
    python = CORE / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(CORE / '.venv')], check=True)
    check = subprocess.run([str(python), '-c', 'import fastapi,pydantic,uvicorn,httpx,yaml,regex,bashlex,pytest'],
                           capture_output=True, encoding='utf-8', errors='replace')
    if check.returncode:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(CORE / 'requirements.lock.txt')], check=True)
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required. Install Node.js, then rerun.')
    if not (DESK / 'node_modules/vite/bin/vite.js').is_file():
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('npm is required for the first dependency installation.')
        subprocess.run([npm, 'ci' if (DESK / 'package-lock.json').exists() else 'install'], cwd=DESK,
                       shell=os.name == 'nt', check=True)
    if not no_build:
        subprocess.run([node, str(DESK / 'node_modules/typescript/bin/tsc')], cwd=DESK, check=True)
        subprocess.run([node, str(DESK / 'node_modules/vite/bin/vite.js'), 'build'], cwd=DESK, check=True)
    if not (DESK / 'dist/index.html').is_file():
        raise RuntimeError('Frontend build missing. Run without --no-build.')
    return str(python), node


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless', action='store_true', help='Start both HTTP services without opening a window')
    parser.add_argument('--web', action='store_true', help='Open default browser instead of Electron')
    parser.add_argument('--no-build', action='store_true', help='Use an already verified dist build')
    parser.add_argument('--smoke-seconds', type=float, default=0, help='Exit and clean up after bounded smoke test')
    args = parser.parse_args(argv)
    children, logs, job = [], [], None
    try:
        for port in (8765, 5173):
            free_port(port)
        python, node = prepare(args.no_build)
        job = ChildJob()
        log_dir = ROOT / 'output/logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        def launch(command, cwd, name):
            log = (log_dir / f'{name}-{time.time_ns()}.log').open('w', encoding='utf-8')
            logs.append(log)
            env = dict(os.environ, PYTHONUTF8='1')
            env.pop('ELECTRON_RUN_AS_NODE', None)
            child = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            children.append(child)
            job.add(child)
            return child
        core = launch([python, 'server.py'], CORE, 'core')
        wait_ready(core, healthy_core, 'CORE 127.0.0.1:8765')
        desk = launch([node, str(DESK / 'node_modules/vite/bin/vite.js'), 'preview', '--host', '127.0.0.1',
                       '--port', '5173', '--strictPort'], DESK, 'desk')
        wait_ready(desk, healthy_desk, 'DESK 127.0.0.1:5173')
        electron = None
        if not args.headless:
            if args.web:
                webbrowser.open('http://127.0.0.1:5173')
            else:
                installed = subprocess.run([node, '-e', "const fs=require('fs'); try { if(!fs.existsSync(require('electron'))) process.exit(1); } catch { process.exit(1); }"],
                    cwd=DESK, capture_output=True, encoding='utf-8', errors='replace')
                if installed.returncode:
                    print('Electron binary unavailable; opening the same desk in the browser. Optional setup: node node_modules/electron/install.js', flush=True)
                    webbrowser.open('http://127.0.0.1:5173')
                else:
                    electron = launch([node, str(DESK / 'node_modules/electron/cli.js'), 'electron/main.cjs'], DESK, 'electron')
        print('D2Guard ready. Ctrl+C stops owned processes. Logs: output/logs', flush=True)
        start, failures = time.monotonic(), 0
        while True:
            if core.poll() is not None or desk.poll() is not None:
                raise RuntimeError('A service exited; stopping its peers. Inspect output/logs.')
            if electron is not None and electron.poll() is not None:
                return electron.returncode
            if args.smoke_seconds and time.monotonic() - start >= args.smoke_seconds:
                return 0
            failures = 0 if healthy_core() and healthy_desk() else failures + 1
            if failures >= 3:
                raise RuntimeError('Service health checks failed three times; stopping peers.')
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'D2Guard startup failed: {exc}', file=sys.stderr, flush=True)
        return 1
    finally:
        for child in reversed(children):
            stop_owned(child)
        if job:
            job.close()
        for log in logs:
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())
