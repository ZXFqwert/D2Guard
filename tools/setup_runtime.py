"""Install the project runtime (Windows or Linux) and configure the local models + provider."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11+ is required; Python 3.12 is recommended')
    sys.path.insert(0, str(ROOT / 'src'))
    # Import-free prerequisite check; bashlex is installed below.
    for command in ('node', 'git'):
        if not shutil.which(command):
            raise RuntimeError(f'Install {command} and add it to PATH, then run setup again')
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise RuntimeError('Install Node.js including npm')
    python = ROOT / ('.venv-windows/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(python.parent.parent)], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT/'requirements-core.txt'),
                    '-r', str(ROOT/'requirements-gpu.txt')], cwd=ROOT, check=True)
    # Use this project's Pi, independently of the machine's global version.
    prefix = ROOT / '.local/pi-runtime'
    subprocess.run([npm, 'install', '--prefix', str(prefix), '--global',
                    '@earendil-works/pi-coding-agent@0.85.1'], cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT/'tools/configure_delivery.py'), '--interactive'], cwd=ROOT, check=True)
    subprocess.run([str(python), '-c', "import sys;sys.path.insert(0,'src');from sandbox_exec import shell_path;print('Shell:',shell_path())"], cwd=ROOT, check=True)
    print('Setup complete. Start the console with ' + ('start-console.bat' if os.name == 'nt' else 'sh start-console.sh'))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Setup failed: {error}', file=sys.stderr)
        sys.exit(1)
