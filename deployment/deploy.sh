#!/usr/bin/env bash
# Run from the current repository root. Runtime data stays outside the checkout.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "${1:-}" == "--pull" ]]; then
    git pull --ff-only
    UPDATED_ROOT="$(git rev-parse --show-toplevel)"
    if [[ "$ROOT" != "$UPDATED_ROOT" && -f "$UPDATED_ROOT/D2guard_core/server.py" ]]; then
        exec bash "$UPDATED_ROOT/deployment/deploy.sh"
    fi
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
Environment=D2GUARD_PREFIX=/safe
Environment=D2GUARD_MANAGED=1
Environment=D2GUARD_FAST_MODEL_PATH=$ROOT/D2guard_core/weights/laya_d2_distilled.json
Environment=D2GUARD_FAST_BACKEND=laya-distilled
Environment=PATH=$ROOT/.venv-server/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$DATA/runtime.env
ExecStart=$ROOT/.venv-server/bin/python deployment/runtime.py --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=3
UMask=0077
[Install]
WantedBy=default.target
EOF
systemctl --user stop d2guard-bridge.service d2guard.service d2guard-tunnel.service 2>/dev/null || true
systemctl --user disable d2guard-bridge.service d2guard.service d2guard-tunnel.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/d2guard-bridge.service" "$HOME/.config/systemd/user/d2guard.service" "$HOME/.config/systemd/user/d2guard-tunnel.service"
systemctl --user daemon-reload
systemctl --user enable --now d2guard-unified.service
systemctl --user restart d2guard-unified.service
for i in {1..30}; do
    if curl --fail --silent http://127.0.0.1:8000/safe/healthz; then
        printf '\nD2Guard ready. Public route: /safe/\n'
        exit 0
    fi
    sleep 1
done
journalctl --user -u d2guard-unified -n 30 --no-pager
exit 1
