# AirSense 10 Reader / AirSense 10 插卡即读报告生成器

macOS + Windows | v1

[English](#english) | [中文](#中文)

---

## English

### What this is

A read-only report generator for the ResMed AirSense 10 SD card.
Insert the card, run the tool, and it generates a complete HTML report:
latest night, daily interpretation, trend chart, previous-night comparison
with a clinical-significance reference column, week / month / quarter /
year modules, nightly table, monthly analysis, and verification checks.

- **Read-only on the card.** The tool never writes to the SD card.
- **Local history.** Nightly results are merged into `output/history.json`,
  so older nights are kept even when the card only retains recent days.
  Re-reading the same date overwrites that date.
- **Used nights only.** Treatment averages use only nights with
  Duration > 0; zero-use days are counted separately and never mixed in.
- **No health data in this repository.** `output/`, including `history.json`
  and `nights.csv`, is git-ignored. Only code and documentation are committed.
- **Daily summary only.** This version reads STR.edf daily summaries, not
  minute-by-minute waveforms; the chart is a per-night trend chart.

### Quick start

**macOS:** double-click `更新AirSense完整报告.command`, or run:

```bash
python3 generate_airsense_report.py
python3 generate_airsense_report.py --sd /Volumes/NO\ NAME --out ./output
```

**Windows:** install Python 3.10+ from python.org (tick
"Add python.exe to PATH"), insert the SD card, then double-click
`run_airsense_report.bat`, or run:

```bat
python generate_airsense_report.py
python generate_airsense_report.py --sd D: --out .\output
```

Without `--sd`, the tool scans for a volume containing `STR.edf`:
macOS scans `/Volumes/*`, Windows scans drive letters C: to Z:.

### Outputs (in `output/`)

- `airsense_report.html` — the complete report.
- `history.json` — merged history by date.
- `nights.csv` — one row per used night, for Excel / Python analysis.

### Definitions (also stated in the report)

- AHI is always a rate: event count / usage hours. A period AHI is
  total events / total hours in the period, not a simple average of nightly AHIs.
- Last 7 / 30 days are counted back from the latest night; month / quarter /
  year are calendar periods.
- SpO2 is left blank when no oximeter is connected, not 0.
- This tool is for data reference only, not diagnosis or pressure advice.
  Pressure changes go through a sleep doctor.

### Verified against a real card copy

- Hundreds of calendar days with used nights and zero-use days, merged
  incrementally without losing older nights.

---

## 中文

### 这是什么

瑞思迈 AirSense 10 呼吸机 SD 卡的只读报告生成器。
插卡后运行，即可生成完整 HTML 报告：最新一晚、每日解读、趋势图、
前日比较（含临床意义参考列）、周 / 月 / 季 / 年模块、每夜总表、
月度分析、核对。

- **只读卡，不写卡。**
- **本地历史。** 每夜结果合并进 `output/history.json`，
  卡上只剩近期时旧夜也不会丢；同一日期重读会覆盖该日期。
- **只用使用夜。** 治疗均值只用时长 > 0 的夜算，零使用日单独计数，不混入。
- **仓库里不放健康数据。** `output/`（含 `history.json`、`nights.csv`）
  已加入 `.gitignore`，只提交代码与说明。
- **每日汇总版。** 本版读 STR.edf 每日汇总，不含分钟波形；曲线图为按夜趋势图。

### 快速开始

**macOS 版：** 双击 `更新AirSense完整报告.command`，或手动跑：

```bash
python3 generate_airsense_report.py
python3 generate_airsense_report.py --sd /Volumes/NO\ NAME --out ./output
```

**Windows 版：** 先装 Python 3.10 以上版本（官网 python.org，安装时勾选
Add python.exe to PATH），插好 SD 卡后双击 `run_airsense_report.bat`，或手动跑：

```bat
python generate_airsense_report.py
python generate_airsense_report.py --sd D: --out .\output
```

不给 `--sd` 时，自动扫描含 `STR.edf` 的卷：
macOS 扫描 `/Volumes/*`，Windows 扫描 C: 至 Z: 盘符。

### 输出（在 `output/` 里）

- `airsense_report.html`：完整报告。
- `history.json`：按日期合并的历史。
- `nights.csv`：每夜一行，供 Excel / Python 再分析。

### 口径（报告里同样写明）

- AHI 一律按小时率；周期 AHI = 周期内事件总数 / 总小时数，
  不是各夜 AHI 的简单平均。
- 近 7 天、近 30 天按最新一晚日期往前数；本月、本季、本年按日历。
- 血氧未接时留空，不填 0。
- 本工具仅作数据参考，不作诊断或调压建议，调压走睡眠医生。

### 已实测

- 真实卡副本：数百个日历日，含使用夜与零使用日，增量合并不丢旧夜。
