"""数据分析和图表生成模块 - 完整版（包含趋势图）"""
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

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'Arial']
plt.rcParams['axes.unicode_minus'] = False


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
                        'channel_2g': [],
                        'channel_5g': [],
                        'channel_6g': [],
                        'noise_2g': [],
                        'noise_5g': [],
                        'noise_6g': []
                    }
                
                # 解析运行时间为秒数
                uptime_str = device.get('uptime', '')
                uptime_seconds = self._parse_uptime_to_seconds(uptime_str)
                
                device_history[serial]['dates'].append(date_obj)
                device_history[serial]['cpu_load'].append(device.get('cpu_load_15m'))
                device_history[serial]['memory_usage'].append(device.get('memory_usage'))
                device_history[serial]['uptime_seconds'].append(uptime_seconds)
                device_history[serial]['client_count'].append(device.get('total_clients', 0))
                
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
                            title: str, ylabel: str, output_path: Path) -> Path:
        """创建趋势图并保存为图片"""
        valid_data = df[[x_col, y_col]].dropna()
        if len(valid_data) < 2:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(valid_data[x_col], valid_data[y_col], marker='o', linewidth=2, markersize=6, color='steelblue')
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.grid(True, alpha=0.3)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        if len(valid_data) > 1:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(valid_data)//5)))
        plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return output_path
    
    def _create_channel_chart(self, df: pd.DataFrame, x_col: str, channel_col: str,
                              title: str, output_path: Path) -> Path:
        """创建信道变化图"""
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
                for serial, history in device_history.items():
                    self._create_device_sheet(writer, serial, history, Path(temp_dir))
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        return excel_path
    
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
            'Clients': history['client_count'],
            '2G_Channel': history['channel_2g'],
            '5G_Channel': history['channel_5g'],
            '6G_Channel': history['channel_6g'],
            '2G_Noise(dB)': history['noise_2g'],
            '5G_Noise(dB)': history['noise_5g'],
            '6G_Noise(dB)': history['noise_6g']
        })
        
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
            # CPU Load Trend
            cpu_path = temp_dir / f"{serial}_cpu.png"
            if self._create_trend_chart(df, 'Date', 'CPU_Load_15m', 'CPU Load Trend', 'CPU Load', cpu_path):
                charts.append(('CPU Load Trend', cpu_path))
            
            # Memory Usage Trend
            mem_path = temp_dir / f"{serial}_memory.png"
            if self._create_trend_chart(df, 'Date', 'Memory_Usage(%)', 'Memory Usage Trend', 'Memory Usage (%)', mem_path):
                charts.append(('Memory Usage Trend', mem_path))
            
            # Clients Trend
            client_path = temp_dir / f"{serial}_clients.png"
            if self._create_trend_chart(df, 'Date', 'Clients', 'Clients Trend', 'Clients', client_path):
                charts.append(('Clients Trend', client_path))
            
            # Uptime Trend
            uptime_path = temp_dir / f"{serial}_uptime.png"
            uptime_col = 'Uptime_Hours'
            if uptime_col in df.columns and self._create_trend_chart(df, 'Date', uptime_col, 'Uptime Trend', 'Uptime (Hours)', uptime_path):
                charts.append(('Uptime Trend', uptime_path))
            
            # 2G Channel Change
            channel_2g_path = temp_dir / f"{serial}_channel_2g.png"
            if self._create_channel_chart(df, 'Date', '2G_Channel', '2G Channel Change', channel_2g_path):
                charts.append(('2G Channel Change', channel_2g_path))
            
            # 5G Channel Change
            channel_5g_path = temp_dir / f"{serial}_channel_5g.png"
            if self._create_channel_chart(df, 'Date', '5G_Channel', '5G Channel Change', channel_5g_path):
                charts.append(('5G Channel Change', channel_5g_path))
        
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
