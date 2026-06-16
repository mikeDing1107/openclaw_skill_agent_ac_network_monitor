#!/bin/bash
# AC网络监控技能 - 一键安装脚本
# 适用于 Ubuntu/Debian 系统

set -e

echo "=========================================="
echo "AC网络监控技能 - 一键安装脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python版本
check_python() {
    echo "1. 检查 Python 环境..."
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        echo -e "${GREEN}✓ Python 已安装: $PYTHON_VERSION${NC}"
    else
        echo -e "${RED}✗ Python3 未安装${NC}"
        echo "   正在安装 Python3..."
        sudo apt update
        sudo apt install -y python3 python3-pip
    fi
}

# 安装系统依赖
install_system_deps() {
    echo ""
    echo "2. 安装系统依赖..."
    
    # 安装 Playwright 系统依赖
    sudo apt update
    sudo apt install -y \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libgbm1 \
        libasound2 \
        libxshmfence1
    echo -e "${GREEN}✓ 系统依赖安装完成${NC}"
}

# 安装Python依赖
install_python_deps() {
    echo ""
    echo "3. 安装 Python 依赖..."
    
    # 升级pip
    pip3 install --upgrade pip
    
    # 安装依赖
    pip3 install -r requirements.txt
    
    echo -e "${GREEN}✓ Python 依赖安装完成${NC}"
}

# 安装Playwright浏览器
install_playwright_browser() {
    echo ""
    echo "4. 安装 Playwright Chromium 浏览器..."
    playwright install chromium
    echo -e "${GREEN}✓ Chromium 浏览器安装完成${NC}"
}

# 验证安装
verify_installation() {
    echo ""
    echo "5. 验证安装..."
    
    # 检查关键模块
    python3 -c "import playwright; print('✓ playwright:', playwright.__version__)" 2>/dev/null || echo "✗ playwright 导入失败"
    python3 -c "import pandas; print('✓ pandas:', pandas.__version__)" 2>/dev/null || echo "✗ pandas 导入失败"
    python3 -c "import matplotlib; print('✓ matplotlib:', matplotlib.__version__)" 2>/dev/null || echo "✗ matplotlib 导入失败"
    python3 -c "import openpyxl; print('✓ openpyxl:', openpyxl.__version__)" 2>/dev/null || echo "✗ openpyxl 导入失败"
    
    echo -e "${GREEN}✓ 验证完成${NC}"
}

# 配置邮件授权码提示
configure_email() {
    echo ""
    echo "6. 邮件配置提示"
    echo "=========================================="
    echo -e "${YELLOW}请手动修改 scripts/ac_monitor.py 中的邮件授权码：${NC}"
    echo ""
    echo "  找到以下行："
    echo "  EMAIL_AUTH_CODE = \"12345678\""
    echo ""
    echo "  替换为您的163邮箱授权码（不是登录密码）"
    echo ""
    echo "  获取方式：163邮箱 → 设置 → POP3/SMTP/IMAP → 开启SMTP → 获取授权码"
    echo "=========================================="
}

# 测试运行提示
test_run() {
    echo ""
    echo "7. 测试运行提示"
    echo "=========================================="
    echo "安装完成后，请运行以下命令测试："
    echo ""
    echo "  # 进入scripts目录，手动运行一次监控"
    echo "  cd scripts"
    echo "  python3 ac_monitor.py"
    echo ""
    echo "  # 设置定时任务（每日9点）"
    echo "  (crontab -l 2>/dev/null; echo '0 9 * * * cd /path/to/agent_ac_network_monitor/scripts && python3 ac_monitor.py >> ../logs/cron.log 2>&1') | crontab -"
    echo "=========================================="
}

# 主流程
main() {
    echo ""
    echo "开始安装..."
    echo ""
    
    check_python
    install_system_deps
    install_python_deps
    install_playwright_browser
    verify_installation
    configure_email
    test_run
    
    echo ""
    echo -e "${GREEN}=========================================="
    echo -e "安装完成！"
    echo -e "==========================================${NC}"
}

# 运行
main