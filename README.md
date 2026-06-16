# AC网络监控技能 (agent_ac_network_monitor)

## 功能概述
- 登录AC网站监控AP设备
- 采集CPU/内存/客户端数/信道等指标
- 每日9点自动生成健康报告并发送邮件
- 生成Excel趋势分析报告

## 安装步骤

### 1. 安装系统依赖
```bash
sudo apt update
sudo apt install -y \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libxshmfence1
```

### 2. 安装Python依赖
```bash
pip3 install -r requirements.txt
playwright install chromium
```

### 3. 配置
编辑 `scripts/ac_monitor.py` 中的：
- `AC_USER` / `AC_PASSWORD` - AC登录账号
- `EMAIL_AUTH_CODE` - 163邮箱SMTP授权码
- `DEST_EMAIL` - 报告接收邮箱

### 4. 运行
```bash
cd scripts
python3 ac_monitor.py
```

## 输出文件
- `data/raw/YYYY-MM-DD_full.json` - 每日原始数据
- `data/trends/ac_trend_report_YYYYMMDD_HHMMSS.xlsx` - 趋势分析Excel报告