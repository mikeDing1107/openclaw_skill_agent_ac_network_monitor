---
name: agent_ac_network_monitor
description: 监控AC管理的AP设备，收集性能数据，生成每日报告和趋势分析Excel
tools: python, playwright, pandas, matplotlib
triggers:
  - 每天09:00:00（北京时间）自动执行
  - 用户说“立即分析AC网络”、“运行AC监控”、“生成网络报告”时手动触发
---

# AC网络设备监控技能

## 功能
1. 登录AC网站，自动处理证书风险
2. 自动翻页获取所有AP设备
3. 采集每个AP的性能数据（内存、客户端、CPU负载、无线射频）
4. 生成每日邮件报告
5. **生成Excel趋势分析报告**（包含每个AP的CPU、内存、客户端、信道变化趋势图）

## 输出文件
- `data/raw/YYYY-MM-DD_full.json` - 每日原始数据
- `data/trends/ac_trend_report_YYYYMMDD_HHMMSS.xlsx` - 趋势分析Excel报告
  - 每个AP一个Sheet
  - 包含数据表格和趋势图
  - 趋势图：CPU负载、内存使用、客户端数、运行时间
  - 信道变化图：2G/5G/6G信道变化

## 安装依赖
```bash
pip3 install -r requirements.txt
playwright install chromium
