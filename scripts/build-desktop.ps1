$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'D2guard_core/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先运行 python start_all.py --smoke-seconds 2 初始化开发依赖。' }
Push-Location $projectRoot
try {
    & $pythonPath -m pip install 'pyinstaller==6.22.3'
    if ($LASTEXITCODE) { throw 'PyInstaller installation failed' }
    & $pythonPath -m PyInstaller --noconfirm --clean --onedir --name D2GuardCore --paths D2guard_core --distpath build/core --workpath build/pyinstaller --specpath build --add-data "${projectRoot}/D2guard_core/policies.yaml;." --add-data "${projectRoot}/D2guard_core/D2guard_contract.json;." --add-data "${projectRoot}/D2guard_core/weights/laya_d2_distilled.json;weights" --hidden-import server --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.http.h11_impl --hidden-import uvicorn.lifespan.on deployment/runtime.py
    if ($LASTEXITCODE) { throw 'Core bundle failed' }
    Push-Location D2guard_desk
    try {
        npm.cmd run build
        if ($LASTEXITCODE) { throw 'Frontend build failed' }
        npm.cmd run package:win
        if ($LASTEXITCODE) { throw 'Desktop package failed' }
    } finally { Pop-Location }
} finally { Pop-Location }
