#!/usr/bin/env bash
# ==============================================================================
# 双镜 D²Guard · 算力机与 Linux 服务器一键部署运维脚本
# 适用环境: Ubuntu / Debian / CentOS / Arch Linux (Python 3.10+)
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

APP_PORT=8000
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$PROJECT_DIR/web_demo.pid"
LOG_FILE="$LOG_DIR/web_demo.log"

mkdir -p "$LOG_DIR"

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   双镜 D²Guard · 智能体攻防演练舱部署管理器         ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] 未检测到 python3，请先安装 Python 3.10+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}[OK] 检测到 Python 版本: ${PYTHON_VERSION}${NC}"

# 2. 检查或创建虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[*] 创建 Python 虚拟环境: $VENV_DIR...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 3. 安装/更新依赖
echo -e "${YELLOW}[*] 检查并安装项目核心依赖 (requirements.txt)...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}[OK] 依赖已就绪！${NC}"

# 4. 检查环境配置文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}[*] 未发现 .env，正在从 .env.example 复制默认模版...${NC}"
        cp .env.example .env
        echo -e "${YELLOW}[!] 请根据需要编辑 .env 填入有效的 LLM_API_KEY${NC}"
    else
        touch .env
    fi
fi

# 控制命令处理
ACTION=${1:-"start"}

start_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}[!] 服务已经在运行中 (PID: $PID)，无需重复启动。${NC}"
            echo -e "${GREEN}访问入口: http://0.0.0.0:${APP_PORT}/safe${NC}"
            exit 0
        else
            rm -f "$PID_FILE"
        fi
    fi

    echo -e "${YELLOW}[*] 正在后台启动 D²Guard Web 演练服务 (端口: ${APP_PORT})...${NC}"
    nohup "$VENV_DIR/bin/python" -m uvicorn web_demo:app --host 0.0.0.0 --port "$APP_PORT" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo "$PID" > "$PID_FILE"

    sleep 2
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}======================================================${NC}"
        echo -e "${GREEN} [SUCCESS] 服务启动成功！PID: ${PID}${NC}"
        echo -e "${GREEN} 本地/内网直连: http://127.0.0.1:${APP_PORT}/safe${NC}"
        echo -e "${GREEN} 算力机 Mesh 地址: http://10.33.0.30:${APP_PORT}/safe${NC}"
        echo -e "${GREEN} 公网反代访问: https://agent.li33.art/safe${NC}"
        echo -e "${GREEN} 日志输出: tail -f ${LOG_FILE}${NC}"
        echo -e "${GREEN}======================================================${NC}"
    else
        echo -e "${RED}[ERROR] 服务启动失败，请检查日志: cat ${LOG_FILE}${NC}"
        exit 1
    fi
}

stop_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}[*] 正在停止服务 (PID: $PID)...${NC}"
            kill "$PID"
            sleep 1
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -9 "$PID"
            fi
            echo -e "${GREEN}[OK] 服务已停止。${NC}"
        else
            echo -e "${YELLOW}[!] 记录的 PID ($PID) 不存在，服务可能未在运行。${NC}"
        fi
        rm -f "$PID_FILE"
    else
        echo -e "${YELLOW}[!] 未找到 PID 文件，尝试按端口查杀...${NC}"
        PIDS=$(lsof -t -i:"$APP_PORT" 2>/dev/null || true)
        if [ -n "$PIDS" ]; then
            kill -9 $PIDS
            echo -e "${GREEN}[OK] 端口 ${APP_PORT} 占用进程已清理。${NC}"
        else
            echo -e "${GREEN}[OK] 无运行中的服务。${NC}"
        fi
    fi
}

status_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}[RUNNING] D²Guard 正在运行 (PID: $PID, 端口: $APP_PORT)${NC}"
            echo -e "${GREEN}内网地址: http://10.33.0.30:${APP_PORT}/safe${NC}"
            echo -e "${GREEN}公网映射: https://agent.li33.art/safe${NC}"
            return 0
        fi
    fi
    echo -e "${RED}[STOPPED] D²Guard 服务未运行。${NC}"
}

dev_service() {
    echo -e "${BLUE}[*] 以开发调试前台模式启动...${NC}"
    exec "$VENV_DIR/bin/python" -m uvicorn web_demo:app --host 0.0.0.0 --port "$APP_PORT" --reload
}

case "$ACTION" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service
        sleep 1
        start_service
        ;;
    status)
        status_service
        ;;
    dev)
        dev_service
        ;;
    log|logs)
        tail -f "$LOG_FILE"
        ;;
    *)
        echo "使用说明: $0 {start|stop|restart|status|dev|logs}"
        exit 1
        ;;
esac
