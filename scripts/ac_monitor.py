#!/usr/bin/env python3
"""
AC网络监控脚本 - 完整修复版
功能：
1. 检查所有AC页面健康状态
2. 分析Dashboard汇总指标
3. 获取所有AP设备详细信息（支持分页）
4. 生成Excel趋势报告并作为附件发送
5. 失败时发送详细错误邮件通知
"""

from playwright.sync_api import sync_playwright
import time
import re
import json
import requests
import urllib3
import traceback
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import smtplib
import sys
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ========== 配置 ==========
AC_URL = "<your-ac-url>"
AC_USER = "<your-ac-username>"
AC_PASSWORD = "<your-ac-password>"

# 邮件配置
SMTP_SERVER = "<your-smtp-server>"
SMTP_PORT = 465
SOURCE_EMAIL = "<your-from-email>"
EMAIL_AUTH_CODE = "<your-smtp-auth-code>"  # SMTP授权码
DEST_EMAIL = "<your-dest-email>"  # 目标邮箱

# 需要检查的页面列表
PAGES_TO_CHECK = [
    {"name": "Home/Device List", "url": AC_URL},
    {"name": "Device Dashboard", "url": f"{AC_URL}#/devices_dashboard"},
    {"name": "Device Blacklist", "url": f"{AC_URL}#/devices_blacklist"},
    {"name": "Batch Config", "url": f"{AC_URL}#/devices_batchconfig"},
    {"name": "Firmware", "url": f"{AC_URL}#/firmware"},
    {"name": "Firmware Dashboard", "url": f"{AC_URL}#/firmware/dashboard"},
    {"name": "Batch Upgrade", "url": f"{AC_URL}#/firmware/batchupgrade"},
    {"name": "Device Logs", "url": f"{AC_URL}#/logs/devices"},
    {"name": "Controller Logs", "url": f"{AC_URL}#/logs/controller"},
    {"name": "Security Logs", "url": f"{AC_URL}#/logs/security"},
    {"name": "Firmware Logs", "url": f"{AC_URL}#/logs/firmware"},
    {"name": "Export Logs", "url": f"{AC_URL}#/logs/export"},
    {"name": "User Management", "url": f"{AC_URL}#/users"},
    {"name": "System Monitoring", "url": f"{AC_URL}#/systemMonitoring"},
    {"name": "Services", "url": f"{AC_URL}#/services"},
]

# 等待时间配置
LOGIN_WAIT = 50
TABLE_LOAD_WAIT = 15
PAGE_LOAD_WAIT = 30
BETWEEN_PAGES_WAIT = 2

DATA_DIR = Path(__file__).parent / "data" / "raw"
TRENDS_DIR = Path(__file__).parent / "data" / "trends"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRENDS_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")

def check_page_health(page, page_info):
    """检查单个页面的健康状态"""
    result = {
        "name": page_info["name"],
        "url": page_info["url"],
        "accessible": False,
        "has_error": False,
        "has_warning": False,
        "error_details": None,
        "warning_details": None,
        "response_time_ms": None
    }
    
    try:
        start_time = time.time()
        response = page.goto(page_info["url"], wait_until="domcontentloaded", timeout=30000)
        end_time = time.time()
        
        result["response_time_ms"] = round((end_time - start_time) * 1000)
        result["accessible"] = True
        
        page_text = page.inner_text('body').lower()
        
        error_keywords = ['error', 'exception', 'failed', '500', '502', '503', '504', 'not found', 'cannot load']
        found_errors = [kw for kw in error_keywords if kw in page_text]
        if found_errors:
            result["has_error"] = True
            result["error_details"] = found_errors
        
        warning_keywords = ['warning', 'warn', 'timeout', 'slow', 'deprecated']
        found_warnings = [kw for kw in warning_keywords if kw in page_text]
        if found_warnings:
            result["has_warning"] = True
            result["warning_details"] = found_warnings
        
        if response:
            result["status_code"] = response.status
            
    except Exception as e:
        result["accessible"] = False
        result["error_details"] = str(e)[:200]
    
    return result

def parse_memory_usage(text):
    """解析内存使用率，从文本中提取百分比数字"""
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    if match:
        return float(match.group(1))
    return None

def parse_cpu_load(text):
    """解析CPU负载，取15分钟平均值（第三个值）"""
    match = re.search(r'Load\s*\([^)]+\):\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)', text)
    if match:
        return float(match.group(3))
    return None

def parse_uptime_from_text(text):
    """解析运行时间"""
    match = re.search(r'Uptime:\s*([^\n]+)', text)
    if match:
        uptime_str = match.group(1).strip()
        uptime_str = re.sub(r'<[^>]+>', '', uptime_str)
        return uptime_str
    return "N/A"

def parse_radios_from_page(page):
    """解析无线射频表格数据"""
    radios = {'2G': {'channel': 'N/A', 'noise': 'N/A'}, '5G': {'channel': 'N/A', 'noise': 'N/A'}}
    
    try:
        radios_section = page.query_selector('h2:has-text("Radios")')
        if radios_section:
            container = radios_section.query_selector('xpath=ancestor::div[contains(@class, "css-")]')
            if container:
                rows = container.query_selector_all('tr')
                for row in rows:
                    row_text = row.inner_text()
                    if row_text.strip().startswith('2G'):
                        cells = row.query_selector_all('td')
                        if len(cells) >= 5:
                            channel = cells[1].inner_text().strip()
                            noise = cells[4].inner_text().strip()
                            if channel.isdigit():
                                radios['2G'] = {'channel': channel, 'noise': noise}
                    elif row_text.strip().startswith('5G'):
                        cells = row.query_selector_all('td')
                        if len(cells) >= 5:
                            channel = cells[1].inner_text().strip()
                            noise = cells[4].inner_text().strip()
                            if channel.isdigit():
                                radios['5G'] = {'channel': channel, 'noise': noise}
    except Exception as e:
        log(f"    解析无线射频失败: {e}")
    
    return radios

def get_device_status(page):
    """获取设备在线/离线状态"""
    page_text = page.inner_text('body').lower()
    if 'disconnected' in page_text:
        return 'offline'
    # 进一步验证：在线设备必须能看到内存和CPU数据
    if 'memory:' not in page_text and 'load (' not in page_text:
        return 'offline'
    return 'online'

def parse_devices_from_page(page):
    """从当前页面解析设备基本信息"""
    devices = []
    
    try:
        page.wait_for_selector('tbody tr', timeout=30000)
        rows = page.query_selector_all('tbody tr')
        
        for row in rows:
            cells = row.query_selector_all('td')
            if len(cells) < 10:
                continue
            
            serial_link = cells[1].query_selector('a')
            if not serial_link:
                continue
            serial = serial_link.inner_text().strip()
            
            sanity_elem = cells[2].query_selector('.css-1ny2kle')
            sanity = sanity_elem.inner_text().strip() if sanity_elem else None
            
            memory_elem = cells[3].query_selector('.css-1ny2kle')
            memory = memory_elem.inner_text().strip().replace('%', '') if memory_elem else None
            
            load_elem = cells[4].query_selector('.css-1ny2kle')
            load = load_elem.inner_text().strip().replace('%', '') if load_elem else None
            
            temp_elem = cells[5].query_selector('.css-1ny2kle')
            temp = temp_elem.inner_text().strip().replace('°C', '') if temp_elem else None
            
            type_elem = cells[7]
            device_type = type_elem.inner_text().strip()
            
            status = 'online' if memory and load else 'offline'
            
            devices.append({
                'serial': serial,
                'type': device_type,
                'status': status,
                'sanity': sanity,
                'memory_usage': float(memory) if memory else None,
                'load': float(load) if load else None,
                'temperature': float(temp) if temp else None
            })
            
    except Exception as e:
        log(f"    解析设备表格失败: {e}")
    
    return devices

def click_next_page(page):
    """点击下一页按钮"""
    try:
        next_button = page.query_selector('button[aria-label="Go to next page"]')
        if not next_button:
            next_button = page.query_selector('button:has-text(">")')
        if next_button and next_button.is_enabled():
            next_button.click()
            time.sleep(5)
            return True
    except Exception as e:
        log(f"    点击下一页失败: {e}")
    return False

def get_all_devices(page):
    """获取所有页面的设备列表"""
    all_devices = []
    page_num = 1
    
    while True:
        log(f"  正在解析第 {page_num} 页...")
        devices = parse_devices_from_page(page)
        log(f"    找到 {len(devices)} 个设备")
        all_devices.extend(devices)
        
        if not click_next_page(page):
            break
        page_num += 1
    
    log(f"总共找到 {len(all_devices)} 个设备")
    return all_devices

def parse_clients_from_associations(page):
    """从Associations表格统计客户端数"""
    clients = {'2G': 0, '5G': 0, '6G': 0}
    
    try:
        tables = page.query_selector_all('table')
        for table in tables:
            rows = table.query_selector_all('tr')
            if len(rows) < 2:
                continue
            header_cells = rows[0].query_selector_all('th, td')
            header_text = ' '.join([cell.inner_text() for cell in header_cells])
            if 'STATION' in header_text and 'SSID' in header_text:
                for row in rows[1:]:
                    cells = row.query_selector_all('td')
                    if len(cells) >= 2:
                        band = cells[0].inner_text().strip()
                        if band == '2G':
                            clients['2G'] += 1
                        elif band == '5G':
                            clients['5G'] += 1
                        elif band == '6G':
                            clients['6G'] += 1
                break
    except Exception as e:
        log(f"    解析客户端统计失败: {e}")
    
    return clients

def _parse_relative_time(text):
    """解析相对时间文本（如 '6 seconds ago', '52 minutes ago'）为总秒数"""
    if not text:
        return None
    text = text.strip().lower()
    # 去除 html 标签
    text = re.sub(r'<[^>]+>', '', text)
    
    # 匹配 "X seconds ago", "X minutes ago", "X hours ago", "X days ago"
    match = re.search(r'(\d+)\s*(second|minute|hour|day)s?\s*ago', text)
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        if unit == 'second':
            return val
        elif unit == 'minute':
            return val * 60
        elif unit == 'hour':
            return val * 3600
        elif unit == 'day':
            return val * 86400
    
    # 匹配纯秒数（如 "30s"）
    match = re.search(r'^(\d+)\s*s$', text)
    if match:
        return int(match.group(1))
    
    return None


def parse_health_checks_scores(page, max_count=50):
    """从Health Checks表格提取健康评分
    
    Args:
        page: Playwright page 对象
        max_count: 最多取最近多少条评分（默认50，约2小时数据）
    
    策略：
    1. 点击Health Checks tab
    2. 点击Show More加载历史数据直到行数 >= max_count
    3. 取最前面max_count条记录的Sanity列评分
    """
    scores = []
    try:
        # 1. 点击Health Checks tab
        health_tab = None
        for selector in [
            'button:has-text("Health Checks")',
            'button[role="tab"]:has-text("Health")',
            'div[role="tab"]:has-text("Health")',
        ]:
            try:
                health_tab = page.query_selector(selector)
                if health_tab and health_tab.is_visible():
                    break
                health_tab = None
            except:
                continue
        
        if health_tab:
            try:
                health_tab.click()
                time.sleep(3)
                log(f"    [DEBUG HEALTH] clicked Health Checks tab via {selector}")
            except:
                pass
        
        # 2. 点击 "Show More" 加载历史数据，直到行数 >= max_count（最多点5次）
        show_more_clicks = 0
        for _ in range(5):
            # 检查当前是否已有足够行数
            tables = page.query_selector_all('table')
            for table in tables:
                rows = table.query_selector_all('tr')
                if len(rows) < 2:
                    continue
                header_cells = rows[0].query_selector_all('th, td')
                header_text = ' '.join([cell.inner_text() for cell in header_cells]).upper()
                if 'SANITY' in header_text or 'HEALTH' in header_text or 'CHECK' in header_text:
                    if len(rows) - 1 >= max_count:
                        break
            else:
                # 行数不够，点Show More
                try:
                    show_more = page.query_selector('button:has-text("Show More")')
                    if not show_more or not show_more.is_visible():
                        break
                    show_more.click()
                    show_more_clicks += 1
                    time.sleep(2)
                    continue
                except:
                    pass
            break  # 行数够了 或 show_more不可用
        if show_more_clicks > 0:
            log(f"    [DEBUG HEALTH] clicked Show More {show_more_clicks}x")
        
        # 3. 查找Health Checks表格
        tables = page.query_selector_all('table')
        found_table = False
        for table in tables:
            rows = table.query_selector_all('tr')
            if len(rows) < 2:
                continue
            header_cells = rows[0].query_selector_all('th, td')
            header_text = ' '.join([cell.inner_text() for cell in header_cells]).upper()
            
            if 'SANITY' in header_text or 'HEALTH' in header_text or 'CHECK' in header_text:
                found_table = True
                # 找Sanity列索引
                sanity_col_idx = None
                for idx, cell in enumerate(header_cells):
                    h = cell.inner_text().upper()
                    if 'SANITY' in h:
                        sanity_col_idx = idx
                if sanity_col_idx is None:
                    sanity_col_idx = 2  # fallback: 第三列
                
                log(f"    [DEBUG HEALTH] found Health table, rows={len(rows)-1}, sanity_col={sanity_col_idx}, show_more_clicks={show_more_clicks}")
                
                total_rows = 0
                for row in rows[1:]:
                    cells = row.query_selector_all('td')
                    if len(cells) <= sanity_col_idx:
                        continue
                    total_rows += 1
                    if total_rows > max_count:
                        break
                    
                    sanity_text = cells[sanity_col_idx].inner_text().strip()
                    score = _parse_sanity_value(sanity_text)
                    if score is not None:
                        scores.append(score)
                
                log(f"    [DEBUG HEALTH] total_rows_loaded={len(rows)-1}, collected={len(scores)} (max={max_count})")
                break
        
        # 策略2：找不到header匹配的表格，尝试扫描
        if not found_table:
            log(f"    [DEBUG HEALTH] strategy 1 failed, trying strategy 2...")
            for table in tables:
                rows = table.query_selector_all('tr')
                if len(rows) < 2:
                    continue
                col_values = {}
                for row in rows[1:]:
                    cells = row.query_selector_all('td')
                    for ci, cell in enumerate(cells):
                        val = _parse_sanity_value(cell.inner_text().strip())
                        if val is not None and 0 <= val <= 100:
                            col_values[ci] = col_values.get(ci, 0) + 1
                
                if col_values:
                    best_col = max(col_values, key=col_values.get)
                    hit_rate = col_values[best_col] / (len(rows) - 1)
                    if hit_rate >= 0.3:
                        log(f"    [DEBUG HEALTH] strategy 2 found col={best_col}, hit_rate={hit_rate:.1%}")
                        for row in rows[1:]:
                            cells = row.query_selector_all('td')
                            if len(cells) > best_col:
                                val = _parse_sanity_value(cells[best_col].inner_text().strip())
                                if val is not None and 0 <= val <= 100:
                                    scores.append(val)
                        break
            
    except Exception as e:
        log(f"    解析Health Checks失败: {e}")
    
    log(f"    [DEBUG HEALTH] final scores ({len(scores)}): {scores[:20]}{'...' if len(scores) > 20 else ''}")
    return scores


def _parse_sanity_value(text):
    """从sanity文本提取健康评分
    
    返回 int (0-100) 或 None（无法解析或非健康评分）
    """
    if not text:
        return None
    text = text.strip()
    
    # 纯数字（0-100）
    if text.isdigit():
        val = int(text)
        if 0 <= val <= 100:
            return val
        return None
    
    # 带%的数字，如 "75%"
    if text.endswith('%'):
        num_part = text[:-1].strip()
        if num_part.isdigit():
            val = int(num_part)
            if 0 <= val <= 100:
                return val
    
    # 文本状态（completed/pass/ok/fail/error等）→ 不计入
    if text.lower() in ['completed', 'pass', 'ok', 'fail', 'error', 'running', 'pending']:
        return None
    
    # 正则提取数字（如 "75%" 已被上面处理，这里处理 "Score: 85" 等）
    # 注意：排除负数（如 "-1"）
    if not text.startswith('-'):
        match = re.search(r'(\d+)', text)
        if match:
            val = int(match.group(1))
            if 0 <= val <= 100:
                return val
    
    return None

def collect_device_detail_metrics(page, serial):
    """采集单个设备的详细指标"""
    detail_url = f"{AC_URL}#/devices/{serial}"
    log(f"  正在采集设备详情: {serial}")
    
    metrics = {
        'name': None,
        'mac': None,
        'uptime': 'N/A',
        'memory_usage': None,
        'cpu_load_15m': None,
        'radios_2g': {'channel': 'N/A', 'noise': 'N/A'},
        'radios_5g': {'channel': 'N/A', 'noise': 'N/A'},
        'health_scores': [],
        'clients_2g': 0,
        'clients_5g': 0,
        'clients_6g': 0,
        'total_clients': 0,
        'traffic': {}
    }
    
    try:
        page.goto(detail_url, wait_until="domcontentloaded")
        time.sleep(PAGE_LOAD_WAIT)
        
        status = get_device_status(page)
        page_text = page.inner_text('body')
        
        # 提取设备名称（Model: 后面跟着设备型号，注意排除 Revision: 等干扰行）
        name_match = re.search(r'Model:\s*(sercomm_\S+|\S+)', page_text, re.IGNORECASE)
        if name_match:
            name_val = name_match.group(1)
            if name_val.lower() not in ('revision:', 'revision'):
                metrics['name'] = name_val
        
        # 提取MAC地址
        mac_match = re.search(r'MAC:\s*([0-9a-f:]{17})', page_text, re.IGNORECASE)
        if mac_match:
            metrics['mac'] = mac_match.group(1)
        
        if status == 'online':
            metrics['memory_usage'] = parse_memory_usage(page_text)
            metrics['uptime'] = parse_uptime_from_text(page_text)
            metrics['cpu_load_15m'] = parse_cpu_load(page_text)
            
            radios = parse_radios_from_page(page)
            metrics['radios_2g'] = radios['2G']
            metrics['radios_5g'] = radios['5G']
            
            metrics['health_scores'] = parse_health_checks_scores(page)
            
            # 采集24小时上行口流量统计
            access_token = page.evaluate('() => sessionStorage.getItem("access_token") || ""')
            metrics['traffic'] = collect_traffic_stats(access_token, serial)
            
            clients = parse_clients_from_associations(page)
            metrics['clients_2g'] = clients['2G']
            metrics['clients_5g'] = clients['5G']
            metrics['clients_6g'] = clients['6G']
            metrics['total_clients'] = clients['2G'] + clients['5G'] + clients['6G']
            
            log(f"    状态: 在线, 内存: {metrics['memory_usage']}%, "
                f"客户端: {metrics['total_clients']}, "
                f"CPU负载: {metrics['cpu_load_15m']}, "
                f"健康评分数量: {len(metrics['health_scores'])}, "
                f"流量接口数: {len(metrics['traffic'])}")
        else:
            metrics['uptime'] = 'N/A'
            log(f"    状态: 离线")
        
        return metrics
    except Exception as e:
        log(f"    采集详情失败: {e}")
        return {
            'serial': serial,
            'name': serial,
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


def collect_traffic_stats(access_token, serial):
    """通过REST API采集AP过去24小时的上行口流量统计
    
    统一口径：per-client 无线客户端加和（与页面 Statistics 图表一致）
    数据来源：
    1. interfaces[up*].ssids[].associations[].rx_bytes/tx_bytes → VLAN分口
    2. link-state.upstream.WAN.counters → WAN口总流量（仅参考，不做趋势图）
    """
    if not access_token:
        return {}
    
    try:
        now = datetime.now()
        start_ms = int((now - timedelta(hours=24)).timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)
        
        headers = {'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}
        url = f'https://acdemo.sercomm.com:16002/api/v1/device/{serial}/statistics'
        params = {'start': start_ms, 'end': end_ms}
        
        resp = requests.get(url, headers=headers, params=params, verify=False, timeout=60)
        if resp.status_code != 200:
            log(f"    [TRAFFIC] API error: {resp.status_code}")
            return {}
        
        data = resp.json()
        records = data.get('data', [])
        if not records:
            return {}
        
        result = {}
        
        # VLAN分口流量：per-client 无线客户端加和
        client_stats = {}  # {(iface_name, mac): {first_rx, first_tx, last_rx, last_tx}}
        TARGET_IFACES = {'up0v149', 'up1v53'}
        
        for i, rec in enumerate(records):
            for iface in rec.get('data', {}).get('interfaces', []):
                iface_name = iface.get('name', '')
                if iface_name not in TARGET_IFACES:
                    continue
                for ssid in iface.get('ssids', []):
                    for assoc in ssid.get('associations', []):
                        mac = assoc.get('station', '')
                        if not mac:
                            continue
                        key = (iface_name, mac)
                        rx = assoc.get('rx_bytes', 0)
                        tx = assoc.get('tx_bytes', 0)
                        if key not in client_stats:
                            client_stats[key] = {'first_rx': rx, 'first_tx': tx, 'last_rx': rx, 'last_tx': tx}
                        else:
                            client_stats[key]['last_rx'] = rx
                            client_stats[key]['last_tx'] = tx
        
        # 按 VLAN 汇总 24h delta
        vlan_totals = {}
        for (iface_name, mac), stats in client_stats.items():
            rx_d = _compute_delta(stats['first_rx'], stats['last_rx'])
            tx_d = _compute_delta(stats['first_tx'], stats['last_tx'])
            if iface_name not in vlan_totals:
                vlan_totals[iface_name] = {'rx': 0, 'tx': 0}
            vlan_totals[iface_name]['rx'] += rx_d
            vlan_totals[iface_name]['tx'] += tx_d
        
        for iface_name in sorted(vlan_totals.keys()):
            totals = vlan_totals[iface_name]
            rx_mb = round(totals['rx'] / (1024 * 1024), 2)
            tx_mb = round(totals['tx'] / (1024 * 1024), 2)
            if rx_mb > 0 or tx_mb > 0:
                result[iface_name] = {'rx_mb': rx_mb, 'tx_mb': tx_mb}
        
        # WAN 口总流量（物理口计数器，仅参考）
        first_ls = records[0]['data'].get('link-state', {})
        last_ls = records[-1]['data'].get('link-state', {})
        first_wan = first_ls.get('upstream', {}).get('WAN', {}).get('counters', {})
        last_wan = last_ls.get('upstream', {}).get('WAN', {}).get('counters', {})
        
        wan_rx = _compute_delta(first_wan.get('rx_bytes', 0), last_wan.get('rx_bytes', 0))
        wan_tx = _compute_delta(first_wan.get('tx_bytes', 0), last_wan.get('tx_bytes', 0))
        if wan_rx > 0 or wan_tx > 0:
            result['WAN'] = {'rx_mb': round(wan_rx / (1024 * 1024), 2),
                            'tx_mb': round(wan_tx / (1024 * 1024), 2)}
        
        log(f"    [TRAFFIC] {serial}: {len(records)} recs, {len(result)} ifaces")
        for name in ['WAN', 'up0v149', 'up1v53']:
            if name in result:
                s = result[name]
                log(f"      {name}: RX={s['rx_mb']:.1f}MB TX={s['tx_mb']:.1f}MB")
        
        return result
        
    except Exception as e:
        log(f"    [TRAFFIC] failed: {e}")
        return {}


def _compute_delta(first_val, last_val):
    """计算累计计数器差值，处理重置"""
    if last_val >= first_val:
        return last_val - first_val
    else:
        return last_val


def parse_dashboard_metrics_from_homepage(page):
    """从首页解析Dashboard汇总指标"""
    metrics = {
        "total_devices": None,
        "avg_uptime": None,
        "total_clients_2g": 0,
        "total_clients_5g": 0,
        "total_clients_6g": 0,
        "device_memory_usage": []
    }
    
    try:
        page_text = page.inner_text('body')
        
        conn_match = re.search(r'Connected Devices\s+(\d+)', page_text)
        if conn_match:
            metrics["total_devices"] = int(conn_match.group(1))
        
        uptime_match = re.search(r'Average Uptime\s+([\d:]+)', page_text)
        if uptime_match:
            metrics["avg_uptime"] = uptime_match.group(1)
        
        # 从表格中解析所有在线AP的内存使用率
        rows = page.query_selector_all('tbody tr')
        log(f"    [DEBUG MEMORY] Parsing {len(rows)} rows from Dashboard table")
        for row in rows:
            cells = row.query_selector_all('td')
            if len(cells) >= 3:
                memory_elem = cells[3].query_selector('.css-1ny2kle')
                if memory_elem:
                    memory_text = memory_elem.inner_text().strip()
                    memory_match = re.search(r'([\d.]+)%', memory_text)
                    if memory_match:
                        mem_val = float(memory_match.group(1))
                        metrics["device_memory_usage"].append(mem_val)
                        log(f"    [DEBUG MEMORY] AP memory: {mem_val}%")
        
        log(f"    [DEBUG MEMORY] Total AP count from table: {len(metrics['device_memory_usage'])}")
        
    except Exception as e:
        log(f"    解析Dashboard失败: {e}")
    
    if metrics["device_memory_usage"]:
        avg_memory = sum(metrics["device_memory_usage"]) / len(metrics["device_memory_usage"])
        metrics["avg_memory_usage"] = avg_memory
        log(f"    [DEBUG MEMORY] Calculated avg_memory: {avg_memory:.1f}%")
    else:
        metrics["avg_memory_usage"] = None
    
    return metrics

def generate_trend_report(data_dir, trends_dir):
    """生成趋势分析Excel报告"""
    try:
        from data_analyzer import DataAnalyzer
        analyzer = DataAnalyzer(data_dir, trends_dir)
        excel_path = analyzer.run()
        return excel_path
    except Exception as e:
        log(f"生成趋势报告失败: {e}")
        return None

def send_report_with_attachment(page_health_results, dashboard_metrics, devices_data, excel_attachment=None):
    """发送带附件的邮件报告"""
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    problem_pages = [p for p in page_health_results if not p["accessible"] or p["has_error"] or p["has_warning"] or p.get("has_warning")]
    
    total_clients_from_devices = sum(d.get('total_clients', 0) for d in devices_data)
    total_clients = total_clients_from_devices  # 使用所有AP的客户端加和
    
    clients_display = f"{total_clients} (2G:{dashboard_metrics.get('total_clients_2g', 0)}, 5G:{dashboard_metrics.get('total_clients_5g', 0)}, 6G:{dashboard_metrics.get('total_clients_6g', 0)})"
    
    html = f"""
    <html>
    <head><style>
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .online {{ color: green; }}
        .offline {{ color: red; }}
    </style></head>
    <body>
        <h2>AC Network Monitoring Report</h2>
        <p>Generated: {report_date}</p>
        <p>Detailed trend analysis is attached as Excel file.</p>
        
        <h3>Page Health Check</h3>
    """
    
    if problem_pages:
        html += '<table border="1" cellpadding="5">'
        html += '<tr><th>Page Name</th><th>Status</th><th>Details</th></tr>'
        for page in problem_pages:
            if not page["accessible"]:
                status = 'Inaccessible'
                detail = page["error_details"]
            elif page["has_error"]:
                status = 'Has Error'
                detail = f"Error: {page['error_details']}"
            elif page["has_warning"]:
                status = 'Has Warning'
                detail = f"Warning: {page['warning_details']}"
            else:
                continue
            html += f'<tr><td class="{status}">{page["name"]}</td><td class="{status}">{status}</td><td class="{detail}">{detail}</td></tr>'
        html += '</table>'
    else:
        html += '<p>All pages are accessible without errors or warnings.</p>'
    
    # Calculate avg memory from all devices (not from dashboard table which only has 1 AP)
    online_devices = [d for d in devices_data if d.get('status') == 'online' and d.get('memory_usage') is not None]
    if online_devices:
        avg_memory = sum(d.get('memory_usage', 0) for d in online_devices) / len(online_devices)
    else:
        avg_memory = None
    # Calculate total clients per band from all devices
    total_clients_2g = sum(d.get('clients_2g', 0) for d in devices_data)
    total_clients_5g = sum(d.get('clients_5g', 0) for d in devices_data)
    total_clients_6g = sum(d.get('clients_6g', 0) for d in devices_data)
    total_clients = total_clients_2g + total_clients_5g + total_clients_6g
    
    # Update dashboard_metrics with correct values for JSON persistence
    dashboard_metrics['avg_memory_usage'] = avg_memory
    dashboard_metrics['total_clients_2g'] = total_clients_2g
    dashboard_metrics['total_clients_5g'] = total_clients_5g
    dashboard_metrics['total_clients_6g'] = total_clients_6g
    
    avg_memory_str = f"{avg_memory:.1f}%" if avg_memory else "N/A"
    clients_display = f"{total_clients} (2G:{total_clients_2g}, 5G:{total_clients_5g}, 6G:{total_clients_6g})"
    html += f"""
        
        <h3>Dashboard Summary</h3>
        <table border="1" cellpadding="5">
            <tr><th>Total Devices</th><td>{dashboard_metrics.get('total_devices', 'N/A')} (Online:{dashboard_metrics.get('online_devices', 'N/A')}, Offline:{dashboard_metrics.get('offline_devices', 'N/A')})</td></tr>
            <tr><th>Average Memory Usage</th><td>{avg_memory_str}</td</tr>
            <tr><th>Total Clients</th><td>{clients_display}</td></tr>
        </table>
        
    """
    
    # 收集所有出现过的上行口名称（用于流量表）
    all_upstreams = set()
    for device in devices_data:
        for iface in device.get('traffic', {}):
            all_upstreams.add(iface)
    all_upstreams = sorted(all_upstreams)
    
    html += f"""
        
        <h3>AP Device Details</h3>
        <table border="1" cellpadding="5">
            <tr>
                <th>Serial</th><th>Device Name</th><th>MAC Address</th><th>Status</th>
                <th>Memory</th><th>Clients</th><th>CPU(15m)</th>
                <th>Uptime</th><th>2G Ch/Noise</th><th>5G Ch/Noise</th><th>Health</th>
            </tr>
    """
    
    for device in devices_data:
        status_class = "online" if device.get('status') == 'online' else "offline"
        status_text = "Online" if device.get('status') == 'online' else "Offline"
        
        radio_2g = device.get('radios_2g', {})
        radio_5g = device.get('radios_5g', {})
        
        memory = device.get('memory_usage')
        memory_str = f"{memory}%" if memory is not None else "N/A"
        
        total_clients = device.get('total_clients', 0)
        
        def avg_health(scores):
            if not scores:
                return 'N/A'
            # 过滤掉异常值（只保留0-100之间的值）
            valid_scores = [s for s in scores if 0 <= s <= 100]
            if not valid_scores:
                return 'N/A'
            return round(sum(valid_scores) / len(valid_scores), 1)
        
        html += f"""
            <tr class="{status_class}">
                <td>{device.get('serial', 'N/A')}</td>
                <td>{device.get('name', 'N/A')}</td>
                <td>{device.get('mac', 'N/A')}</td>
                <td>{status_text}</td>
                <td>{memory_str}</td>
                <td>{total_clients}</td>
                <td>{device.get('cpu_load_15m', 'N/A')}</td>
                <td>{device.get('uptime', 'N/A')}</td>
                <td>{radio_2g.get('channel', 'N/A')}/{radio_2g.get('noise', 'N/A')}</td>
                <td>{radio_5g.get('channel', 'N/A')}/{radio_5g.get('noise', 'N/A')}</td>
                <td>{avg_health(device.get('health_scores', []))}</td>
            </tr>
        """
    
    html += """
        </table>
"""
    
    html += """
        <p><small>This report is automatically generated by OpenClaw. Detailed trend analysis (including 24h upstream traffic) is attached.</small></p>
    </body>
    </html>
    """
    
    # 创建邮件
    msg = MIMEMultipart()
    msg['From'] = SOURCE_EMAIL
    msg['To'] = DEST_EMAIL
    msg['Subject'] = f"AC Monitoring Report - {report_date}"
    msg.attach(MIMEText(html, 'html'))
    
    # 添加Excel附件
    if excel_attachment and Path(excel_attachment).exists():
        try:
            with open(excel_attachment, 'rb') as f:
                part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={Path(excel_attachment).name}')
                msg.attach(part)
                log(f"Attached: {Path(excel_attachment).name}")
        except Exception as e:
            log(f"Failed to attach: {e}")
    
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SOURCE_EMAIL, EMAIL_AUTH_CODE)
            server.send_message(msg)
        log("Email sent successfully")
        return True
    except Exception as e:
        log(f"Email failed: {e}")
        return False

def send_failure_email(error_message, error_type="AC Network Monitoring Error"):
    """发送失败通知邮件"""
    try:
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 创建邮件内容
        html_content = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>AC监控失败通知</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #ff4444; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ padding: 20px; background-color: #f9f9f9; border-left: 4px solid #ff4444; }}
                .error-details {{ background-color: #ffeeee; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                .timestamp {{ color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ AC网络监控任务失败</h2>
                <p>任务类型: {error_type}</p>
                <p class="timestamp">报告时间: {report_date}</p>
            </div>
            <div class="content">
                <h3>错误详情:</h3>
                <div class="error-details">
                    <p><strong>错误时间:</strong> {report_date}</p>
                    <p><strong>错误类型:</strong> {error_type}</p>
                    <p><strong>错误信息:</strong><br>{error_message}</p>
                </div>
                
                <h3>建议处理措施:</h3>
                <ul>
                    <li>检查网络连接是否正常</li>
                    <li>确认AC网站 (acdemo.sercomm.com:18443) 是否可访问</li>
                    <li>验证登录凭据是否正确</li>
                    <li>检查服务器响应状态</li>
                    <li>如果问题持续，请手动执行脚本进行调试</li>
                </ul>
                
                <p><em>此邮件由AC网络监控系统自动发送</em></p>
            </div>
        </body>
        </html>
        """
        
        # 创建邮件
        msg = MIMEMultipart()
        msg['From'] = SOURCE_EMAIL
        msg['To'] = DEST_EMAIL
        msg['Subject'] = f"⚠️ AC监控失败通知 - {report_date}"
        msg.attach(MIMEText(html_content, 'html'))
        
        # 添加错误日志文件作为附件
        error_log = f"error_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(error_log, 'w', encoding='utf-8') as f:
            f.write(f"AC网络监控失败报告\n")
            f.write(f"时间: {report_date}\n")
            f.write(f"错误类型: {error_type}\n")
            f.write(f"错误信息: {error_message}\n\n")
            f.write(f"系统信息:\n")
            f.write(f"- 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- Python版本: {sys.version}\n")
            f.write(f"- 工作目录: {os.getcwd()}\n")
        
        try:
            with open(error_log, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={error_log}')
                msg.attach(part)
        except Exception as e:
            log(f"Failed to attach error log: {e}")
        
        # 发送邮件
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SOURCE_EMAIL, EMAIL_AUTH_CODE)
            server.send_message(msg)
        
        # 清理临时错误日志文件
        try:
            os.remove(error_log)
        except:
            pass
        
        log(f"Failure notification email sent: {error_type}")
        return True
        
    except Exception as e:
        log(f"Failed to send failure email: {e}")
        return False

def main():
    print("="*60)
    print("AC Network Monitoring Script")
    print("="*60)
    
    start_time = time.time()
    timeout_threshold = 3600  # 1小时超时阈值
    last_progress_time = start_time
    
    all_data = {
        "page_health": [],
        "dashboard_metrics": {},
        "devices": []
    }
    
    def check_timeout():
        """检查是否超时"""
        current_time = time.time()
        if current_time - last_progress_time > timeout_threshold:
            error_msg = f"脚本执行超时（{timeout_threshold}秒）\n\n最后进度时间: {datetime.fromtimestamp(last_progress_time).strftime('%Y-%m-%d %H:%M:%S')}\n当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n可能原因:\n1. 网络连接问题\n2. AC网站响应缓慢\n3. 设备数量过多导致采集时间过长"
            send_failure_email(error_msg, "AC网络监控超时")
            raise TimeoutError(f"Script execution timed out after {timeout_threshold} seconds")
    
    def log_progress(step):
        """记录进度并检查超时"""
        nonlocal last_progress_time
        current_time = time.time()
        last_progress_time = current_time
        log(f"进度: {step}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--ignore-certificate-errors',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-extensions',
                '--no-zygote',
            ]
        )
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(120000)
        
        try:
            # 1. 登录
            log("1. Logging in...")
            page.goto(AC_URL, wait_until="domcontentloaded")
            time.sleep(10)
            
            page.fill("input[type='text']", AC_USER)
            page.fill("input[type='password']", AC_PASSWORD)
            page.click("button[type='submit']")
            
            log(f"   Waiting {LOGIN_WAIT}s for login...")
            time.sleep(LOGIN_WAIT)
            log("   Login successful")
            log_progress("登录完成")
            
            # 2. 检查所有页面健康状态
            log("2. Checking page health...")
            for i, page_info in enumerate(PAGES_TO_CHECK):
                log(f"   [{i+1}/{len(PAGES_TO_CHECK)}] Checking: {page_info['name']}")
                result = check_page_health(page, page_info)
                all_data["page_health"].append(result)
                if not result["accessible"]:
                    log(f"      Inaccessible")
                elif result["has_error"]:
                    log(f"      Has error")
                elif result["has_warning"]:
                    log(f"      Has warning")
                else:
                    log(f"      OK")
            log_progress("页面健康检查完成")
            
            # 3. 返回首页获取设备列表
            log("3. Returning to home page...")
            page.goto(AC_URL, wait_until="domcontentloaded")
            log(f"   Waiting {TABLE_LOAD_WAIT}s for table...")
            time.sleep(TABLE_LOAD_WAIT)
            
            # 4. 获取所有设备的列表
            log("4. Getting device list...")
            devices_list = get_all_devices(page)
            log_progress("设备列表获取完成")
            
            # 5. 计算Dashboard汇总指标
            log("5. Calculating Dashboard summary...")
            all_data["dashboard_metrics"] = parse_dashboard_metrics_from_homepage(page)
            
            online_count = sum(1 for d in devices_list if d.get('status') == 'online')
            all_data["dashboard_metrics"]["online_devices"] = online_count
            all_data["dashboard_metrics"]["offline_devices"] = len(devices_list) - online_count
            all_data["dashboard_metrics"]["total_devices"] = len(devices_list)
            
            log(f"   Dashboard: Total={all_data['dashboard_metrics'].get('total_devices')}, Online={online_count}")
            log_progress("Dashboard指标计算完成")
            
            # 6. 采集每个设备的详细信息
            log(f"6. Collecting details for {len(devices_list)} devices...")
            for i, device in enumerate(devices_list):
                log(f"   [{i+1}/{len(devices_list)}]")
                detail = collect_device_detail_metrics(page, device['serial'])
                combined = {**device, **detail}
                all_data["devices"].append(combined)
                if i < len(devices_list) - 1:
                    time.sleep(BETWEEN_PAGES_WAIT)
                
                # 每采集5个设备检查一次超时
                if (i + 1) % 5 == 0:
                    log_progress(f"已采集 {i+1}/{len(devices_list)} 个设备")
                    check_timeout()
            
            # 7. 保存原始数据
            log("7. Saving raw data...")
            today = date.today().isoformat()
            # Update dashboard_metrics with correct values before saving
            online_devices = [d for d in all_data["devices"] if d.get("status") == "online" and d.get("memory_usage") is not None]
            all_data["dashboard_metrics"]["avg_memory_usage"] = sum(d.get("memory_usage", 0) for d in online_devices) / len(online_devices) if online_devices else None
            all_data["dashboard_metrics"]["total_clients_2g"] = sum(d.get("clients_2g", 0) for d in all_data["devices"])
            all_data["dashboard_metrics"]["total_clients_5g"] = sum(d.get("clients_5g", 0) for d in all_data["devices"])
            all_data["dashboard_metrics"]["total_clients_6g"] = sum(d.get("clients_6g", 0) for d in all_data["devices"])
            data_file = DATA_DIR / f"{today}_full.json"
            with open(data_file, 'w') as f:
                json.dump(all_data, f, indent=2, default=str)
            log(f"   Data saved to {data_file}")
            log_progress("原始数据保存完成")
            
            # 8. 生成趋势分析Excel报告
            log("8. Generating trend analysis report...")
            excel_path = generate_trend_report(DATA_DIR, TRENDS_DIR)
            if excel_path:
                log(f"   Trend report generated: {excel_path}")
            else:
                log("   Trend report generation failed (need at least 2 days of data)")
            log_progress("Excel报告生成完成")
            
            # 9. 发送邮件报告（带Excel附件）
            log("9. Sending email report...")
            send_report_with_attachment(
                all_data["page_health"],
                all_data["dashboard_metrics"],
                all_data["devices"],
                excel_path
            )
            log_progress("邮件发送完成")
            
            elapsed = time.time() - start_time
            print("\n" + "="*60)
            print("Monitoring completed!")
            print(f"   Pages checked: {len(all_data['page_health'])}")
            print(f"   Devices found: {len(all_data['devices'])}")
            print(f"   Online devices: {online_count}")
            print(f"   Offline devices: {len(all_data['devices']) - online_count}")
            print(f"   Total time: {elapsed/60:.1f} minutes")
            if excel_path:
                print(f"   Trend report: {excel_path}")
            print("="*60)
            
        except TimeoutError as te:
            error_msg = f"AC监控执行超时: {str(te)}"
            log(f"Monitoring timeout: {te}")
            log(f"Error details: {error_msg}")
            
            # 发送超时通知邮件
            send_failure_email(error_msg, "AC网络监控超时")
            
            sys.exit(1)
        except Exception as e:
            error_msg = f"AC监控执行失败: {str(e)}\n\n详细错误信息:\n{traceback.format_exc()}"
            log(f"Monitoring failed: {e}")
            log(f"Error details: {error_msg}")
            
            # 发送失败通知邮件
            send_failure_email(error_msg, "AC网络监控执行失败")
            
            traceback.print_exc()
            
            # 退出状态码1表示失败
            sys.exit(1)
        finally:
            try:
                browser.close()
            except:
                pass

if __name__ == "__main__":
    main()
