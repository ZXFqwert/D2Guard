#!/usr/bin/env bash
# Run inside the checked-out unified edition. No secrets or private dependencies in Git.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "${1:-}" == "--pull" ]]; then
    git pull --ff-only
fi
python3 -m venv .venv-server
.venv-server/bin/python -m pip install -r D2guard_core/requirements.lock.txt
(cd D2guard_desk && npm ci --include=dev --ignore-scripts && npm run build:web)
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/d2guard-unified"
mkdir -p "$DATA/workspace" "$HOME/.config/systemd/user"
chmod 700 "$DATA"
if [[ ! -e "$DATA/runtime.env" ]]; then
    printf '%s\n' 'D2GUARD_ORIGINS=https://agent.li33.art' > "$DATA/runtime.env"
    chmod 600 "$DATA/runtime.env"
fi
cat > "$HOME/.config/systemd/user/d2guard-unified.service" <<EOF
[Unit]
Description=D2Guard unified web edition
After=network-online.target
[Service]
WorkingDirectory=$ROOT
Environment=D2GUARD_DB=$DATA/d2guard.sqlite3
Environment=D2GUARD_EXEC_ROOT=$DATA/workspace
Environment=D2GUARD_STATIC=$ROOT/D2guard_desk/dist-web
Environment=D2GUARD_PREFIX=/safe/desk
Environment=D2GUARD_MANAGED=1
Environment=PATH=$ROOT/.venv-server/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$DATA/runtime.env
ExecStart=$ROOT/.venv-server/bin/python deployment/runtime.py --port 8766
Restart=on-failure
RestartSec=3
UMask=0077
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now d2guard-unified.service
systemctl --user restart d2guard-unified.service
for i in {1..30}; do
    if curl --fail --silent http://127.0.0.1:8766/safe/desk/healthz; then
        printf '\nD2Guard ready. Public route: /safe/desk/\n'
        exit 0
    fi
    sleep 1
done
journalctl --user -u d2guard-unified -n 30 --no-pager
exit 1
