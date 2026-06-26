# Changelog

## [1.0.3] - 2026-06-26
### Added
- **24h 上行口流量统计**：通过 REST API (`/api/v1/device/{serial}/statistics`) 采集每个 AP 过去 24 小时的上行口流量
  - WAN 口：物理口计数器差值
  - up0v149 / up1v53 VLAN 分口：per-client 无线客户端加和口径，与页面 Statistics 图表一致
  - 结果以 MB 为单位保存至 `traffic` 字段
- **Traffic Summary Sheet**：Excel 报告中新增流量汇总表，集中展示所有 AP 的 WAN / up0v149 / up1v53 RX/TX 流量
- **Per-AP 流量趋势图**：每个 AP 的 Sheet 中增加各 VLAN 接口的 RX+TX 合并趋势图（含平均值参考线）

## [1.0.2] - 2026-06-24
### Fixed
- `parse_health_checks_scores()`: 修复健康评分采集间歇性返回空数组的问题
  1. 解析逻辑bug：纯数字值如 `75`、`25` 之前被错误跳过（`isdigit()` 路径只接受 `0`），所有 0-100 的数值现在均正确采集
  2. 添加多策略表格定位：优先按header关键字匹配，失败后自动扫描所有表格找Sanity-like列
  3. Health Checks tab 点击添加多种selector回退（button/text/role）
  4. 提取 `_parse_sanity_value()` 为独立函数，统一处理各种格式（纯数字、百分比、Score: XX等）
### Changed
- 健康评分采样数从 ~25 条 → 固定 **50 条**（约 2 小时数据）
  1. 自动点击 "Show More" 按钮加载历史数据直到行数 >= 50
  2. 取最新 50 条记录的 Sanity 列评分

## [1.0.1] - 2026-06-18
### Added
- Temperature trend chart for each AP device
- Threshold lines (Warning/Error) for CPU Load, Memory Usage, and Temperature trends
- Average reference line for CPU Load, Memory Usage, Temperature, and Clients trends
- Configurable thresholds via `threshold_config.yaml`

## [1.0.0] - 2026-06-16
### Changed
- Official release after 3 weeks of stable operation

## [0.0.3] - 2026-06-05
### Fixed
- Login timeout issue
- AP page display issue (intermittent)
### Removed
- Statistics section
- Useless legacy files

## [0.0.2] - 2026-05-26
### Added
- Raw data collection
- Trend Excel generation
- Email report
### Changed
- Basic architecture completed

## [0.0.1] - 2026-05-20
### Added
- Initial version
