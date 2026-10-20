"""Start the configured Windows console with live Agent tools enabled."""
import argparse
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ.update(D2_HOST_EXEC='1', PYTHONUTF8='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    prefix = ROOT / '.local/pi-runtime'
    if (prefix / 'node_modules/@earendil-works/pi-coding-agent/package.json').is_file():
        os.environ['NPM_CONFIG_PREFIX'] = str(prefix)
    missing = [name for name in ('provider.json','laya.json','s1.json') if not (ROOT/'.local'/name).is_file()]
    if missing:
        print('Live execution needs setup-windows.bat. Historical evidence remains available.', flush=True)
    sys.path.insert(0, str(ROOT/'console'))
    sys.path.insert(0, str(ROOT/'src'))
    sys.argv = ['server.py','--repo',str(ROOT),'--port',str(args.port),'--python',sys.executable]
    os.environ['D2_OPEN_BROWSER'] = '0' if args.no_browser else '1'
    runpy.run_path(str(ROOT/'console/server.py'), run_name='__main__')


if __name__ == '__main__':
    main()
