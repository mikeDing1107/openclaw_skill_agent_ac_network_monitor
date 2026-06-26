"""数据分析和图表生成模块 - 完整版（包含趋势图和阈值线）"""
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from openpyxl.drawing.image import Image
import tempfile
import shutil
import yaml

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'Arial']
plt.rcParams['axes.unicode_minus'] = False

# 配置文件路径
SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent
THRESHOLD_CONFIG_FILE = SKILL_DIR / 'threshold_config.yaml'


def load_threshold_config() -> dict:
    """加载阈值配置文件"""
    default_config = {
        'thresholds': {
            'memory_usage': {'average': True, 'warning': 50, 'error': 80, 'show_warning': True, 'show_error': True},
            'cpu_load': {'average': True, 'warning': 80, 'error': 95, 'show_warning': True, 'show_error': True},
            'temperature': {'average': True, 'warning': 70, 'error': 85, 'show_warning': True, 'show_error': True},
            'clients': {'average': True, 'show_warning': False, 'show_error': False}
        },
        'line_styles': {
            'average': {'color': '#555555', 'linestyle': '--', 'linewidth': 1.5, 'label': 'Average'},
            'warning': {'color': '#FFA500', 'linestyle': '-', 'linewidth': 1.5, 'label': 'Warning'},
            'error': {'color': '#FF0000', 'linestyle': '-', 'linewidth': 2, 'label': 'Error'}
        },
        'chart_config': {'dpi': 150, 'figure_width': 10, 'figure_height': 5}
    }
    
    if THRESHOLD_CONFIG_FILE.exists():
        try:
            with open(THRESHOLD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
                # 深度合并配置
                merged = default_config.copy()
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in merged:
                        merged[key].update(value)
                    else:
                        merged[key] = value
                return merged
        except Exception as e:
            print(f"警告: 阈值配置文件加载失败，使用默认配置: {e}")
            return default_config
    else:
        print(f"提示: 阈值配置文件不存在，使用默认配置: {THRESHOLD_CONFIG_FILE}")
        return default_config


THRESHOLD_CONFIG = load_threshold_config()


class DataAnalyzer:
    """数据分析和图表生成器"""
    
    def __init__(self, data_dir: Path, output_dir: Path):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def load_all_data(self) -> dict:
        """加载所有历史数据文件"""
        all_data = {}
        json_files = sorted(self.data_dir.glob("*_full.json"))
        
        print(f"找到 {len(json_files)} 个数据文件")
        
        for json_file in json_files:
            date_str = json_file.stem.replace("_full", "")
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    except:
                        continue
                    all_data[date_obj] = data
                    print(f"  加载: {date_str} - {len(data.get('devices', []))} 个设备")
            except Exception as e:
                print(f"  加载 {json_file} 失败: {e}")
        
        return all_data
    
    def build_device_history(self, all_data: dict) -> dict:
        """按设备组织历史数据"""
        device_history = {}
        
        for date_obj, data in all_data.items():
            devices = data.get('devices', [])
            for device in devices:
                serial = device.get('serial')
                if not serial:
                    continue
                
                if serial not in device_history:
                    device_history[serial] = {
                        'name': device.get('name', serial),
                        'mac': device.get('mac', serial),
                        'dates': [],
                        'cpu_load': [],
                        'memory_usage': [],
                        'uptime_seconds': [],
                        'client_count': [],
                        'temperature': [],
                        'channel_2g': [],
                        'channel_5g': [],
                        'channel_6g': [],
                        'noise_2g': [],
                        'noise_5g': [],
                        'noise_6g': [],
                        'traffic': {}
                    }
                
                # 解析运行时间为秒数
                uptime_str = device.get('uptime', '')
                uptime_seconds = self._parse_uptime_to_seconds(uptime_str)
                
                device_history[serial]['dates'].append(date_obj)
                device_history[serial]['cpu_load'].append(device.get('cpu_load_15m'))
                device_history[serial]['memory_usage'].append(device.get('memory_usage'))
                device_history[serial]['uptime_seconds'].append(uptime_seconds)
                device_history[serial]['client_count'].append(device.get('total_clients', 0))
                device_history[serial]['temperature'].append(device.get('temperature'))
                
                # 信道数据
                radios_2g = device.get('radios_2g', {})
                radios_5g = device.get('radios_5g', {})
                radios_6g = device.get('radios_6g', {})
                
                device_history[serial]['channel_2g'].append(radios_2g.get('channel', 'N/A'))
                device_history[serial]['channel_5g'].append(radios_5g.get('channel', 'N/A'))
                device_history[serial]['channel_6g'].append(radios_6g.get('channel', 'N/A'))
                device_history[serial]['noise_2g'].append(radios_2g.get('noise', 'N/A'))
                device_history[serial]['noise_5g'].append(radios_5g.get('noise', 'N/A'))
                device_history[serial]['noise_6g'].append(radios_6g.get('noise', 'N/A'))
                
                # 流量数据处理：对齐日期，确保所有接口有对应日期的值
                traffic = device.get('traffic', {})
                # 收集当前日期出现的所有接口
                seen_ifaces = set(device_history[serial]['traffic'].keys()) | set(traffic.keys())
                for iface in seen_ifaces:
                    if iface not in device_history[serial]['traffic']:
                        device_history[serial]['traffic'][iface] = {'rx_mb': [], 'tx_mb': []}
                    # 补齐之前缺失的日期（用0填充）
                    expected_len = len(device_history[serial]['dates']) - 1
                    while len(device_history[serial]['traffic'][iface]['rx_mb']) < expected_len:
                        device_history[serial]['traffic'][iface]['rx_mb'].append(0)
                        device_history[serial]['traffic'][iface]['tx_mb'].append(0)
                    # 添加当前日期的值
                    stats = traffic.get(iface, {})
                    device_history[serial]['traffic'][iface]['rx_mb'].append(stats.get('rx_mb', 0))
                    device_history[serial]['traffic'][iface]['tx_mb'].append(stats.get('tx_mb', 0))
        
        return device_history
    
    def _parse_uptime_to_seconds(self, uptime_str: str) -> float:
        """将运行时间字符串转换为秒数"""
        if not uptime_str or uptime_str == 'N/A':
            return np.nan
        try:
            if 'Days' in uptime_str:
                parts = uptime_str.split(',')
                days = int(parts[0].strip().split()[0])
                time_part = parts[1].strip()
                h, m, s = map(int, time_part.split(':'))
                return days * 86400 + h * 3600 + m * 60 + s
            elif ':' in uptime_str:
                parts = uptime_str.split(':')
                if len(parts) == 3:
                    h, m, s = map(int, parts)
                    return h * 3600 + m * 60 + s
        except:
            pass
        return np.nan
    
    def _create_trend_chart(self, df: pd.DataFrame, x_col: str, y_col: str, 
                            title: str, ylabel: str, output_path: Path,
                            chart_type: str = None) -> Path:
        """创建趋势图并保存为图片（支持阈值线和平均值线）"""
        valid_data = df[[x_col, y_col]].dropna()
        if len(valid_data) < 2:
            return None
        
        # 获取图表配置
        chart_cfg = THRESHOLD_CONFIG.get('chart_config', {})
        dpi = chart_cfg.get('dpi', 150)
        fig_width = chart_cfg.get('figure_width', 10)
        fig_height = chart_cfg.get('figure_height', 5)
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        
        # 绘制主数据线
        ax.plot(valid_data[x_col], valid_data[y_col], marker='o', linewidth=2, markersize=6, color='steelblue', label='Actual')
        
        # 获取阈值配置
        thresholds = THRESHOLD_CONFIG.get('thresholds', {})
        line_styles = THRESHOLD_CONFIG.get('line_styles', {})
        
        # 根据chart_type获取对应的阈值配置
        if chart_type is None:
            chart_type = self._get_chart_type(y_col)
        
        threshold_cfg = thresholds.get(chart_type, {})
        show_average = threshold_cfg.get('average', False)
        show_warning = threshold_cfg.get('show_warning', False)
        show_error = threshold_cfg.get('show_error', False)
        
        # 获取数据值的范围，用于决定是否显示某些线
        y_values = valid_data[y_col].values
        y_min, y_max = np.nanmin(y_values), np.nanmax(y_values)
        
        # 绘制平均值线
        if show_average:
            avg_style = line_styles.get('average', {})
            avg_value = np.nanmean(y_values)
            # 只有当平均值在数据范围内时有意义才显示
            if y_min <= avg_value <= y_max * 1.5:
                ax.axhline(y=avg_value, 
                          color=avg_style.get('color', 'gray'),
                          linestyle=avg_style.get('linestyle', '--'),
                          linewidth=avg_style.get('linewidth', 1.5),
                          label=avg_style.get('label', 'Average'))
        
        # 绘制Warning线
        if show_warning and 'warning' in threshold_cfg:
            warn_value = threshold_cfg['warning']
            warn_style = line_styles.get('warning', {})
            # 只有当Warning值在数据范围内或略高于数据时才显示
            if y_min <= warn_value <= y_max * 1.2:
                ax.axhline(y=warn_value,
                          color=warn_style.get('color', '#FFA500'),
                          linestyle=warn_style.get('linestyle', '-'),
                          linewidth=warn_style.get('linewidth', 1.5),
                          label=warn_style.get('label', 'Warning'))
        
        # 绘制Error线（只要数据接近或超过Error阈值就显示，全超标也保留警示）
        if show_error and 'error' in threshold_cfg:
            error_value = threshold_cfg['error']
            error_style = line_styles.get('error', {})
            if error_value <= y_max * 1.5:
                ax.axhline(y=error_value,
                          color=error_style.get('color', '#FF0000'),
                          linestyle=error_style.get('linestyle', '-'),
                          linewidth=error_style.get('linewidth', 2),
                          label=error_style.get('label', 'Error'))
        
        # 设置图表标题和标签
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.grid(True, alpha=0.3)
        
        # 添加图例
        ax.legend(loc='upper right', fontsize=10)
        
        # 设置X轴日期格式
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        if len(valid_data) > 1:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(valid_data)//5)))
        plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _get_chart_type(self, y_col: str) -> str:
        """根据y列名获取chart类型"""
        y_col_lower = y_col.lower()
        if 'memory' in y_col_lower:
            return 'memory_usage'
        elif 'cpu' in y_col_lower:
            return 'cpu_load'
        elif 'temperature' in y_col_lower or 'temp' in y_col_lower:
            return 'temperature'
        elif 'client' in y_col_lower:
            return 'clients'
        return 'default'
    
    def _create_channel_chart(self, df: pd.DataFrame, x_col: str, channel_col: str,
                              title: str, output_path: Path) -> Path:
        """创建信道变化图（不带阈值线）"""
        channel_values = []
        valid_dates = []
        
        for idx, row in df.iterrows():
            channel = row[channel_col]
            if channel and channel != 'N/A':
                try:
                    if ',' in str(channel):
                        channel = str(channel).split(',')[0]
                    channel_num = float(channel)
                    channel_values.append(channel_num)
                    valid_dates.append(row[x_col])
                except (ValueError, TypeError):
                    pass
        
        if len(channel_values) < 2:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(valid_dates, channel_values, marker='o', linewidth=2, markersize=8, color='orange')
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Channel', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        # Set y-axis ticks to valid channel ranges
        if '2G' in title:
            ax.set_ylim(0, 14)
            ax.set_yticks([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
        elif '5G' in title:
            ax.set_ylim(30, 170)
            ax.set_yticks([36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 149, 153, 157, 161, 165])
        
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        if len(valid_dates) > 1:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(valid_dates)//5)))
        plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _create_combined_traffic_chart(self, dates, rx_vals, tx_vals, iface_name, output_path):
        """创建合并 RX+TX 流量趋势图（双线 + 双均值参考线）"""
        df = pd.DataFrame({'Date': dates, 'RX': rx_vals, 'TX': tx_vals})
        # 至少需要 2 个数据点，且至少有 1 个非零值
        if len(df) < 2:
            return None
        if sum(df['RX']) == 0 and sum(df['TX']) == 0:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 5))
        
        ax.plot(df['Date'], df['RX'], marker='o', linewidth=2, markersize=5, color='#2196F3', label='RX')
        ax.plot(df['Date'], df['TX'], marker='s', linewidth=2, markersize=5, color='#FF5722', label='TX')
        
        avg_rx = np.mean(df['RX'])
        avg_tx = np.mean(df['TX'])
        ax.axhline(y=avg_rx, color='#2196F3', linestyle='--', linewidth=1, alpha=0.6, label=f'RX avg ({avg_rx:.1f} MB)')
        ax.axhline(y=avg_tx, color='#FF5722', linestyle='--', linewidth=1, alpha=0.6, label=f'TX avg ({avg_tx:.1f} MB)')
        
        ax.set_title(f'{iface_name} Traffic (24h)', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('MB', fontsize=12)
        ax.legend(loc='upper left', fontsize=9)
        ax.grid(True, alpha=0.3)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        if len(df) > 1:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(df)//5)))
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        return output_path
    
    def generate_excel_report(self, device_history: dict) -> Path:
        """生成Excel报告，返回文件路径"""
        if not device_history:
            print("警告: 没有设备历史数据，无法生成Excel报告")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = self.output_dir / f"ac_trend_report_{timestamp}.xlsx"
        
        # 创建临时目录用于存放图表
        temp_dir = tempfile.mkdtemp()
        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # 首先创建流量汇总Sheet
                self._create_traffic_summary_sheet(writer, device_history)
                for serial, history in device_history.items():
                    self._create_device_sheet(writer, serial, history, Path(temp_dir))
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        return excel_path
    
    def _create_traffic_summary_sheet(self, writer, device_history: dict):
        """创建流量汇总Sheet - 显示最近一天所有AP的上行口流量"""
        if not device_history:
            return
        
        # 收集所有接口名称和最新日期的流量数据
        iface_order = ['WAN', 'up0v149', 'up1v53']
        all_ifaces = set()
        rows = []
        for serial, history in device_history.items():
            traffic = history.get('traffic', {})
            for iface in traffic:
                if iface in iface_order:
                    all_ifaces.add(iface)
            
            if history['dates']:
                latest_idx = len(history['dates']) - 1
                row_data = {
                    'Serial': serial,
                    'Name': history.get('name', serial),
                    'Date': history['dates'][latest_idx].strftime('%Y-%m-%d')
                }
                for iface in iface_order:
                    data = traffic.get(iface)
                    if data and latest_idx < len(data['rx_mb']):
                        row_data[f'{iface}_RX(MB)'] = data['rx_mb'][latest_idx]
                        row_data[f'{iface}_TX(MB)'] = data['tx_mb'][latest_idx]
                rows.append(row_data)
        
        if not rows:
            return
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Traffic Summary', index=False)
        
        # 调整列宽
        worksheet = writer.sheets['Traffic Summary']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 3, 25)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    def _create_device_sheet(self, writer, serial: str, history: dict, temp_dir: Path):
        """为单个设备创建Sheet"""
        sheet_name = f"{serial[-8:]}" if len(serial) > 8 else serial
        if len(sheet_name) > 31:
            sheet_name = sheet_name[:31]
        
        # 创建DataFrame - 列名使用英文
        df = pd.DataFrame({
            'Date': history['dates'],
            'CPU_Load_15m': history['cpu_load'],
            'Memory_Usage(%)': history['memory_usage'],
            'Uptime_Hours': [s / 3600 if not np.isnan(s) else np.nan for s in history['uptime_seconds']],
            'Temperature(°C)': history['temperature'],
            'Clients': history['client_count'],
            '2G_Channel': history['channel_2g'],
            '5G_Channel': history['channel_5g'],
            '6G_Channel': history['channel_6g'],
            '2G_Noise(dB)': history['noise_2g'],
            '5G_Noise(dB)': history['noise_5g'],
            '6G_Noise(dB)': history['noise_6g']
        })
        
        # 添加 VLAN 流量数据列（up0v149 + up1v53，WAN 只在 Traffic Summary 中）
        traffic = history.get('traffic', {})
        for iface in ['up0v149', 'up1v53']:
            if iface in traffic:
                it = traffic[iface]
                rx_vals = it.get('rx_mb', [])
                tx_vals = it.get('tx_mb', [])
                if len(rx_vals) == len(df):
                    df[f'{iface}_RX(MB)'] = rx_vals
                if len(tx_vals) == len(df):
                    df[f'{iface}_TX(MB)'] = tx_vals
        
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
        worksheet = writer.sheets[sheet_name]
        
        # 调整列宽
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        charts = []
        
        if len(df) >= 2:
            # CPU Load Trend (带阈值线)
            cpu_path = temp_dir / f"{serial}_cpu.png"
            if self._create_trend_chart(df, 'Date', 'CPU_Load_15m', 'CPU Load Trend', 'CPU Load', cpu_path, chart_type='cpu_load'):
                charts.append(('CPU Load Trend', cpu_path))
            
            # Memory Usage Trend (带阈值线)
            mem_path = temp_dir / f"{serial}_memory.png"
            if self._create_trend_chart(df, 'Date', 'Memory_Usage(%)', 'Memory Usage Trend', 'Memory Usage (%)', mem_path, chart_type='memory_usage'):
                charts.append(('Memory Usage Trend', mem_path))
            
            # Clients Trend (带平均值线)
            client_path = temp_dir / f"{serial}_clients.png"
            if self._create_trend_chart(df, 'Date', 'Clients', 'Clients Trend', 'Clients', client_path, chart_type='clients'):
                charts.append(('Clients Trend', client_path))
            
            # Uptime Trend (不带阈值线)
            uptime_path = temp_dir / f"{serial}_uptime.png"
            uptime_col = 'Uptime_Hours'
            if uptime_col in df.columns and self._create_trend_chart(df, 'Date', uptime_col, 'Uptime Trend', 'Uptime (Hours)', uptime_path):
                charts.append(('Uptime Trend', uptime_path))
            
            # Temperature Trend (带阈值线)
            temp_path = temp_dir / f"{serial}_temperature.png"
            if self._create_trend_chart(df, 'Date', 'Temperature(°C)', 'Temperature Trend', 'Temperature (°C)', temp_path, chart_type='temperature'):
                charts.append(('Temperature Trend', temp_path))
            
            # 2G Channel Change (不带阈值线)
            channel_2g_path = temp_dir / f"{serial}_channel_2g.png"
            if self._create_channel_chart(df, 'Date', '2G_Channel', '2G Channel Change', channel_2g_path):
                charts.append(('2G Channel Change', channel_2g_path))
            
            # 5G Channel Change (不带阈值线)
            channel_5g_path = temp_dir / f"{serial}_channel_5g.png"
            if self._create_channel_chart(df, 'Date', '5G_Channel', '5G Channel Change', channel_5g_path):
                charts.append(('5G Channel Change', channel_5g_path))
            
            # Traffic Trend Charts: 每个 VLAN RX+TX 合并一张图，WAN 不做图
            traffic = history.get('traffic', {})
            for iface in sorted(traffic.keys()):
                if iface == 'WAN':
                    continue
                iface_traffic = traffic[iface]
                rx_vals = iface_traffic.get('rx_mb', [])
                tx_vals = iface_traffic.get('tx_mb', [])
                if len(df) != len(rx_vals) or len(df) != len(tx_vals):
                    continue
                has_data = any(v != 0 for v in rx_vals) or any(v != 0 for v in tx_vals)
                if not has_data:
                    continue
                path = temp_dir / f"{serial}_{iface}_traffic.png"
                if self._create_combined_traffic_chart(df['Date'], rx_vals, tx_vals, iface, path):
                    charts.append((f'{iface} RX+TX Traffic', path))
        
        # Insert charts into Excel
        if charts:
            start_row = len(df) + 3
            for i, (title, chart_path) in enumerate(charts):
                if chart_path.exists():
                    row_offset = start_row + i * 22
                    worksheet.cell(row=row_offset, column=1, value=title)
                    img = Image(str(chart_path))
                    img.width = 600
                    img.height = 350
                    worksheet.add_image(img, f'B{row_offset+1}')
        else:
            start_row = len(df) + 3
            worksheet.cell(row=start_row, column=1, value="Note: At least 2 days of data required for trend charts")
    
    def run(self) -> Path:
        """运行完整的数据分析流程，返回Excel文件路径"""
        print("=" * 60)
        print("正在分析历史数据...")
        print("=" * 60)
        
        all_data = self.load_all_data()
        print(f"共加载 {len(all_data)} 天的数据")
        
        if len(all_data) == 0:
            print("错误: 没有找到任何数据文件，请先运行 ac_monitor.py 采集数据")
            return None
        
        device_history = self.build_device_history(all_data)
        print(f"找到 {len(device_history)} 个设备的历史数据")
        
        if len(device_history) == 0:
            print("错误: 没有找到任何设备数据")
            return None
        
        excel_path = self.generate_excel_report(device_history)
        if excel_path:
            print(f"Excel报告已生成: {excel_path}")
        else:
            print("Excel报告生成失败")
        
        return excel_path


if __name__ == "__main__":
    from pathlib import Path
    data_dir = Path("./data/raw")
    output_dir = Path("./data/trends")
    
    analyzer = DataAnalyzer(data_dir, output_dir)
    result = analyzer.run()
    if result:
        print(f"\n成功生成: {result}")
    else:
        print("\n生成失败，请检查数据文件")
