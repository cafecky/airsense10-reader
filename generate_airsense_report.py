#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AirSense 10 complete data reader and report generator v1 (macOS + Windows)
AirSense 10 完整数据读取与报告生成器 v1（macOS 版 + Windows 版）

Reads a ResMed AirSense 10 SD card (STR.edf daily summary), merges local
history, and generates a complete HTML report: daily interpretation, trend
chart, previous-night comparison with a clinical-significance reference
column, week / month / quarter / year modules, nightly table, monthly
analysis, and verification checks.
读取瑞思迈 AirSense 10 的 SD 卡（STR.edf 每日汇总），合并本地历史，生成完整
HTML 报告：每日解读、趋势图、前日比较（含临床意义参考列）、周 / 月 / 季 /
年模块、每夜总表、月度分析、核对。

Read-only on the card. Only used nights (Duration > 0) enter treatment
averages; zero-use days are counted separately and never mixed in.
只读卡，不写卡；治疗均值只用使用夜（时长 > 0）算，零使用日单独计数，不混入。

Usage / 用法：
  python3 generate_airsense_report.py [--sd /Volumes/NO NAME | D:] [--out DIR]
  Without --sd, scans for STR.edf: macOS /Volumes/*, Windows drives C: to Z:.
  不给 --sd 时自动扫描含 STR.edf 的卷：macOS 扫描 /Volumes/*，Windows 扫描 C: 至 Z: 盘符。
"""
import argparse
import csv
import datetime
import glob
import json
import os
import struct
import sys

CST = datetime.timezone(datetime.timedelta(hours=8))
GENERATOR_VERSION = "v1"
DAILY = [
    ("ahi", "AHI"), ("hi", "HI"), ("ai", "AI"), ("oai", "OAI"), ("cai", "CAI"),
    ("uai", "UAI"), ("rin", "RIN"), ("leak", "Leak.50"), ("leak95", "Leak.95"),
    ("leakmax", "Leak.Max"), ("press", "S.C.Press"), ("press95", "BlowPress.95"),
    ("rr", "RespRate.50"), ("tv", "TidVol.50"), ("mv", "MinVent.50"),
    ("dur", "Duration"), ("hours", "PatientHours"), ("spo2", "SpO2.50"),
]


def find_card(sd_arg, scan_roots=None):
    """Find STR.edf. Accepts a card root, a STR.edf file, or auto-scan."""
    if sd_arg:
        if os.path.isfile(sd_arg) and os.path.basename(sd_arg) == "STR.edf":
            return sd_arg
        cand = os.path.join(sd_arg, "STR.edf")
        if os.path.isfile(cand):
            return cand
        raise SystemExit("未在指定路径找到 STR.edf：%s" % sd_arg)
    if scan_roots is None:
        if sys.platform.startswith("win"):
            import string
            scan_roots = ["%s:\\\\" % c for c in string.ascii_uppercase[2:]]
        else:
            scan_roots = sorted(glob.glob("/Volumes/*"))
    for root in scan_roots:
        cand = os.path.join(root, "STR.edf")
        if os.path.isfile(cand):
            return cand
    raise SystemExit("未找到 AirSense 10 卡：请先插卡，或用 --sd 指定卡目录 / STR.edf")


def parse_header(raw):
    return {
        "n_signals": int(raw[252:256].decode("ascii", "ignore").strip() or 0),
        "n_records": int(raw[236:244].decode("ascii", "ignore").strip() or 0),
    }


def _txt(raw, st, sz, ns):
    return [raw[st + i * sz:st + i * sz + sz].decode("ascii", "ignore").strip()
            for i in range(ns)]


def _num(raw, st, sz, ns, cast):
    out = []
    for i in range(ns):
        s = raw[st + i * sz:st + i * sz + sz].decode("ascii", "ignore").strip()
        try:
            out.append(cast(s) if s else cast(0))
        except ValueError:
            out.append(cast(0))
    return out


def layout_col(raw, ns):
    lbl = 256
    dim = lbl + ns * 16 + ns * 80
    pmin = dim + ns * 8
    pmax = pmin + ns * 8
    dmin = pmax + ns * 8
    dmax = dmin + ns * 8
    pref = dmax + ns * 8
    nsamp = pref + ns * 80
    data = nsamp + ns * 8 + ns * 32
    return (data, _txt(raw, lbl, 16, ns), _txt(raw, dim, 8, ns),
            _num(raw, pmin, 8, ns, float), _num(raw, pmax, 8, ns, float),
            _num(raw, dmin, 8, ns, int), _num(raw, dmax, 8, ns, int),
            _num(raw, nsamp, 8, ns, int), "colmajor")


def layout_row(raw, ns):
    labels, dims, pmin, pmax, dmin, dmax, nsamp = [], [], [], [], [], [], []
    for i in range(ns):
        b = 256 + i * 256
        labels.append(raw[b:b + 16].decode("ascii", "ignore").strip())
        dims.append(raw[b + 96:b + 104].decode("ascii", "ignore").strip())
        pmin.append(float(raw[b + 104:b + 112].decode("ascii", "ignore").strip() or 0))
        pmax.append(float(raw[b + 112:b + 120].decode("ascii", "ignore").strip() or 0))
        dmin.append(int(raw[b + 120:b + 128].decode("ascii", "ignore").strip() or 0))
        dmax.append(int(raw[b + 128:b + 136].decode("ascii", "ignore").strip() or 0))
        nsamp.append(int(raw[b + 216:b + 224].decode("ascii", "ignore").strip() or 0))
    return (256 + ns * 256, labels, dims, pmin, pmax, dmin, dmax, nsamp, "rowmajor")


def load_edf(path):
    with open(path, "rb") as f:
        raw = f.read()
    size = len(raw)
    meta = parse_header(raw)
    ns, nr = meta["n_signals"], meta["n_records"]
    pick = None
    for fn in (layout_col, layout_row):
        try:
            c = fn(raw, ns)
        except Exception:
            continue
        rec = sum(c[7]) * 2
        if rec and c[0] + nr * rec == size:
            pick = c
            break
    if pick is None:
        raise SystemExit("无法识别 EDF 布局: %s" % path)
    off0, labels, dims, pmin, pmax, dmin, dmax, nsamp, layout = pick
    series = {label: [] for label in labels}
    off = off0
    for _ in range(nr):
        for i in range(ns):
            c = nsamp[i]
            if c == 0:
                continue
            vals = struct.unpack("<" + "h" * c, raw[off:off + c * 2])
            off += c * 2
            span = (dmax[i] - dmin[i]) or 1
            phys = [pmin[i] + (v - dmin[i]) * (pmax[i] - pmin[i]) / span for v in vals]
            series[labels[i]].append(phys[0])
    return {"labels": labels, "dims": dims, "series": series, "size": size}


def build_days(edf):
    s = edf["series"]
    dims = dict(zip(edf["labels"], edf["dims"]))
    dates = s.get("Date") or []
    out = []
    for i in range(len(dates)):
        try:
            d = (datetime.date(1970, 1, 1) + datetime.timedelta(days=int(round(dates[i])))).isoformat()
        except Exception:
            d = "unknown"
        row = {"d": d}
        for key, ch in DAILY:
            v = s.get(ch)
            if not v or i >= len(v):
                continue
            x = v[i]
            if dims.get(ch, "").strip() == "L/s":
                x *= 60.0
            if key != "spo2" and x < 0:
                x = 0.0
            row[key] = round(x, 3)
        out.append(row)
    return out


def fmt(v, nd=2):
    if v is None:
        return "—"
    return ("%.*f" % (nd, v)).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def delta(a, b):
    if a is None or b is None:
        return "—"
    return "%+.2f" % (a - b)


def ahi_range(a):
    if a is None:
        return "AHI 未算出"
    if a < 5:
        return "AHI 在 5/小时以下正常范围"
    if a < 15:
        return "AHI 在 5-15/小时轻度范围"
    if a < 30:
        return "AHI 在 15-30/小时中度范围"
    return "AHI 在 30/小时以上重度范围"


def period_stats(nights):
    if not nights:
        return None
    hours = sum(n["dur"] / 60.0 for n in nights)
    events = sum(n["ahi"] * n["dur"] / 60.0 for n in nights if n.get("ahi") is not None)
    def avg(key):
        vals = [n[key] for n in nights if n.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    return {"nights": len(nights), "hours": round(hours, 1),
            "ahi": round(events / hours, 2) if hours else None,
            "avg_hours": avg("dur_hours"), "avg_leak95": avg("leak95"),
            "avg_press95": avg("press95")}


def to_night(row):
    dur = row.get("dur", 0) or 0
    spo2 = row.get("spo2")
    return {
        "date": row["d"], "dur": dur, "dur_hours": round(dur / 60.0, 2),
        "hours": round(dur / 60.0, 2),
        "ahi": row.get("ahi"), "hi": row.get("hi"), "ai": row.get("ai"),
        "oai": row.get("oai"), "cai": row.get("cai"), "uai": row.get("uai"),
        "leak": row.get("leak"), "leak95": row.get("leak95"), "leakmax": row.get("leakmax"),
        "press": row.get("press"), "press95": row.get("press95"),
        "rr": row.get("rr"), "tv": round(row["tv"] * 1000, 0) if row.get("tv") is not None else None, "mv": row.get("mv"),
        "spo2": None if spo2 is None or spo2 < 0 else spo2,
    }


def night_interp(n, prev_n):
    parts = ["%s，%s 小时，AHI %s/小时，%s。" % (n["date"], fmt(n["dur_hours"]), fmt(n["ahi"]), ahi_range(n["ahi"])),
             "事件：阻塞 %s、中央 %s、低通气 %s。" % (fmt(n["oai"]), fmt(n["cai"]), fmt(n["hi"]))]
    if (n["cai"] or 0) == 0:
        parts.append("本夜无中枢性事件，事件以阻塞性为主。")
    if n.get("leak95") is not None:
        parts.append("漏气 95%% %s L/min%s。" % (fmt(n["leak95"]), "，面罩密封较好" if n["leak95"] <= 24 else "，偏高，留意面罩贴合"))
    if n.get("press95") is not None:
        parts.append("95%% 压力 %s cmH2O，潮气量中位 %s ml。" % (fmt(n["press95"]), fmt(n["tv"])))
    if prev_n and n["ahi"] is not None and prev_n["ahi"] is not None:
        d = n["ahi"] - prev_n["ahi"]
        parts.append("与上一使用夜（%s，AHI %s）相比，AHI %s%s。" % (
            prev_n["date"], fmt(prev_n["ahi"]),
            "上升 " if d > 0 else "下降 " if d < 0 else "持平", fmt(abs(d)) if d else ""))
    parts.append("以上只作参考，不作诊断或调压建议。")
    return "".join(parts)


def clin(label, a, b, latest, prev):
    if label == "AHI（/小时）":
        if a is not None and b is not None and a < 5 and b < 5:
            return "两晚均在 5/小时以下正常范围；单夜变化属正常波动，看趋势不看单夜。"
        if a is not None and a >= 5:
            return "最新一晚达到 5/小时以上，需结合多夜趋势并咨询睡眠医生，单夜不能定论。"
        return "AHI 为事件数 / 使用小时数。"
    if label == "阻塞 / 中央 / 低通气":
        if (latest["cai"] or 0) == 0 and (prev["cai"] or 0) == 0:
            return "两晚均无中枢性事件；事件以阻塞性为主，中央成分未见信号。"
        return "含中枢性事件时，压力调整需医生结合整体评估，不宜自行加压。"
    if label == "漏气 95%（L/min）":
        if a is not None and b is not None and a < b:
            return "漏气 95% 下降，面罩密封较上一晚好。"
        if a is not None and a > 24:
            return "漏气 95% 偏高，留意面罩贴合与夜间口漏。"
        return "漏气 95% 反映整夜大部分时间的漏气水平。"
    if label == "95% 压力（cmH2O）":
        return "95% 压力反映整夜大部分时间的压力水平，AutoSet 会随事件自动调整。"
    if label == "使用时长（小时）":
        return "使用时长为机器开机治疗时长，不是入睡时长。"
    return "中位值基本稳定，小幅变化在夜间正常波动范围内。"


def build_html(nights, calendar_days, zero_days, generated):
    nights_sorted = sorted(nights, key=lambda n: n["date"])
    latest = nights_sorted[-1] if nights_sorted else None
    prev = nights_sorted[-2] if len(nights_sorted) >= 2 else None
    latest_date = datetime.date.fromisoformat(latest["date"]) if latest else None

    def in_window(days):
        if not latest_date:
            return []
        return [n for n in nights_sorted if (latest_date - datetime.date.fromisoformat(n["date"])).days < days]
    def in_month():
        return [n for n in nights_sorted if n["date"][:7] == latest["date"][:7]]
    def in_quarter():
        m = int(latest["date"][5:7]); q = (m - 1) // 3
        return [n for n in nights_sorted if n["date"][:4] == latest["date"][:4] and (int(n["date"][5:7]) - 1) // 3 == q]
    def in_year():
        return [n for n in nights_sorted if n["date"][:4] == latest["date"][:4]]
    periods = [("近 7 天", in_window(7)), ("近 30 天", in_window(30)),
               ("本月", in_month()), ("本季", in_quarter()), ("本年", in_year())]
    period_data = {label: period_stats(ns) for label, ns in periods}
    interp_data = {}
    for idx, n in enumerate(nights_sorted):
        prev_n = nights_sorted[idx - 1] if idx > 0 else None
        interp_data[n["date"]] = {"title": "%s · %s 小时" % (n["date"], fmt(n["dur_hours"])),
                                   "text": night_interp(n, prev_n)}
    trend = {"dates": [n["date"] for n in nights_sorted],
             "ahi": [n["ahi"] for n in nights_sorted],
             "leak95": [n["leak95"] for n in nights_sorted],
             "press95": [n["press95"] for n in nights_sorted],
             "dur": [n["dur_hours"] for n in nights_sorted]}
    report_json = json.dumps({"interp": interp_data, "periods": period_data, "trend": trend}, ensure_ascii=False)
    night_opts = "".join('<option value="%s"%s>%s</option>' % (n["date"], " selected" if latest and n["date"] == latest["date"] else "", n["date"]) for n in nights_sorted)
    comp_summary = ""
    if latest and prev and latest["ahi"] is not None and prev["ahi"] is not None:
        if latest["ahi"] < 5 and prev["ahi"] < 5:
            comp_summary = ("总体参考：两晚 AHI 分别为 %s 与 %s/小时，均在 5 以下正常范围；"
                            "单夜变化属正常波动，结论需等更多夜数形成趋势，并由睡眠医生结合症状判断。" % (fmt(prev["ahi"]), fmt(latest["ahi"])))
        else:
            comp_summary = "总体参考：最新一晚 AHI 较高，建议积累多夜数据后咨询睡眠医生，勿自行调压。"
    comp_rows = ""
    if latest and prev:
        pairs = [("使用时长（小时）", latest["dur_hours"], prev["dur_hours"]),
                 ("AHI（/小时）", latest["ahi"], prev["ahi"]),
                 ("阻塞 / 中央 / 低通气", None, None),
                 ("漏气 95%（L/min）", latest["leak95"], prev["leak95"]),
                 ("漏气最高（L/min）", latest["leakmax"], prev["leakmax"]),
                 ("95% 压力（cmH2O）", latest["press95"], prev["press95"]),
                 ("潮气量中位（ml）", latest["tv"], prev["tv"]),
                 ("呼吸频率中位", latest["rr"], prev["rr"])]
        for label, a, b in pairs:
            if a is None and b is None:
                comp_rows += ("<tr><td>%s</td><td>%s / %s / %s</td><td>%s / %s / %s</td><td>—</td><td>%s</td></tr>\n" % (
                    label, fmt(latest["oai"]), fmt(latest["cai"]), fmt(latest["hi"]),
                    fmt(prev["oai"]), fmt(prev["cai"]), fmt(prev["hi"]), clin(label, None, None, latest, prev)))
            else:
                comp_rows += "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (
                    label, fmt(a), fmt(b), delta(a, b), clin(label, a, b, latest, prev))
    else:
        comp_rows = "<tr><td colspan='5'>历史里只有一晚，前日比较在第二晚读卡后自动出现。</td></tr>"
    night_rows = ""
    for n in reversed(nights_sorted):
        night_rows += ("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s / %s / %s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (
            n["date"], fmt(n["dur_hours"]), fmt(n["ahi"]), fmt(n["oai"]), fmt(n["cai"]), fmt(n["hi"]),
            fmt(n["leak95"]), fmt(n["press95"]), fmt(n["tv"])))
    month_rows = ""
    months = {}
    for n in nights_sorted:
        months.setdefault(n["date"][:7], []).append(n)
    for mon in sorted(months):
        s = period_stats(months[mon])
        month_rows += "<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (
            mon, s["nights"], s["hours"], fmt(s["ahi"]), fmt(s["avg_leak95"]))
    mode_note = "AirSense 10 AutoSet：本报告数据源自卡上 STR.edf 每日汇总，不含波形细节；血氧未接时留空，不填 0。"
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirSense 10呼吸机数据分析报告</title>
<style>
:root{--bg:#f5f7fa;--fg:#0f172a;--mut:#64748b;--line:#e2e8f0;--blue:#2563eb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);line-height:1.7;
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:40px 20px 60px}
.hero{background:linear-gradient(135deg,#1e3a8a,#2563eb 55%%,#0ea5e9);color:#fff;
border-radius:16px;padding:30px 32px;margin-bottom:24px}
.hero h1{margin:0 0 8px;font-size:27px;text-align:center}
.hero p{margin:0;font-size:14px;opacity:.93;text-align:center}
.hero .meta{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;font-size:13px;justify-content:center}
.hero .meta span{background:rgba(255,255,255,.15);padding:4px 10px;border-radius:999px}
.layout{display:grid;grid-template-columns:280px 1fr;gap:18px;align-items:start}
.sidebar{position:sticky;top:16px;display:flex;flex-direction:column;gap:18px}
.sidebar .card{padding:18px 20px}
.nav a{display:block;padding:5px 0;color:var(--blue);text-decoration:none;font-size:13px}
@media(max-width:900px){.layout{grid-template-columns:1fr}.sidebar{position:static}}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px}
.card h2{margin:0 0 6px;font-size:17px;color:var(--blue)}
.card p{margin:0 0 10px;font-size:13px;color:var(--mut)}
.tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:999px;
background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;margin-right:6px}
.section{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-top:24px}
.section h3{margin:0 0 14px;font-size:16px;color:var(--blue)}
.ctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}
.ctl select{font-size:14px;padding:6px 10px;border:1px solid var(--line);border-radius:8px}
.mbtn{font-size:13px;padding:6px 12px;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;border-radius:999px;cursor:pointer}
.mbtn.on{background:#2563eb;color:#fff;border-color:#2563eb}
#chart{width:100%%;height:auto;border:1px solid var(--line);border-radius:10px;background:#fff}
#tip{position:absolute;background:#0f172a;color:#fff;font-size:12px;padding:6px 10px;border-radius:8px;display:none;pointer-events:none;white-space:nowrap}
.chartwrap{position:relative}
table{width:100%%;border-collapse:collapse;font-size:13px;margin-top:6px}
th,td{border:1px solid var(--line);padding:6px 8px}
th{background:#eff6ff;color:#1d4ed8;text-align:center}
td{text-align:left}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px 18px;
font-size:13px;color:#92400e;margin-top:20px}
.note code{background:#fef3c7;padding:1px 5px;border-radius:4px}
.note ul{margin:8px 0 0;padding-left:20px}
footer{margin-top:26px;font-size:12px;color:var(--mut);text-align:center}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <h1>AirSense 10呼吸机数据分析报告</h1>
    <p>插卡即读：自动合并本地历史，卡上只剩最新一天时旧夜也不会丢；前日、周、月、季、年分析一次生成。</p>
    <div class="meta">
      <span>生成: %s</span>
      <span>版本: v1</span>
      <span>设备: AirSense 10 AutoSet</span>
      <span>使用夜: %d / 日历日 %d</span>
      <span>最新一晚: %s</span>
    </div>
  </header>

  <div class="layout">
  <aside class="sidebar">
    <div class="card">
      <h2>最新一晚</h2>
      <p>%s，%s 小时，AHI %s/小时，阻塞 %s、中央 %s、低通气 %s，漏气 95%% %s，95%% 压力 %s。</p>
      <span class="tag">AirSense 10</span><span class="tag">STR.edf</span>
    </div>
    <div class="card">
      <h2>模式与口径</h2>
      <p>%s</p>
      <span class="tag">AHI 按小时率</span><span class="tag">零使用日不计入均值</span>
    </div>
    <div class="card">
      <h2>区块导航</h2>
      <nav class="nav">
        <a href="#interp">一、每日分析解读</a>
        <a href="#chartsec">二、数据图形分析说明</a>
        <a href="#compare">三、前日比较</a>
        <a href="#period">四、周 / 月 / 季 / 年分析</a>
        <a href="#nights">五、每夜总表</a>
        <a href="#months">六、月度分析</a>
        <a href="#checks">七、核对</a>
      </nav>
    </div>
  </aside>
  <div class="maincol">
  <div class="section" id="interp">
    <h3>一、每日分析解读 · 选择日期</h3>
    <div class="ctl"><label>日期 <select id="interpSel"></select></label></div>
    <p id="interpTitle" style="font-weight:600"></p>
    <p id="interpText" style="font-size:14px"></p>
  </div>

  <div class="section" id="chartsec">
    <h3>二、数据图形分析说明 · 选择指标看趋势</h3>
    <p style="font-size:13px;color:var(--mut)">每夜一个点，数据源自卡上 STR.edf 每日汇总（不是分钟波形）；横轴为日期，纵轴随指标自动缩放；鼠标移到曲线上可看该夜数值。</p>
    <div class="ctl">
      <span id="metricBtns">
        <button class="mbtn on" data-i="ahi">AHI</button>
        <button class="mbtn" data-i="leak95">漏气 95%%</button>
        <button class="mbtn" data-i="press95">95%% 压力</button>
        <button class="mbtn" data-i="dur">使用时长</button>
      </span>
    </div>
    <div class="chartwrap"><canvas id="chart" width="940" height="360"></canvas><div id="tip"></div></div>
    <p id="chartInfo" style="font-size:13px;color:var(--mut)"></p>
  </div>

  <div class="section" id="compare">
    <h3>三、前日比较 · 最新一晚 vs 上一使用夜</h3>
    <p style="font-size:13px;color:var(--mut)">%s</p>
    <table>
      <tr><th>指标</th><th>最新一晚</th><th>上一晚</th><th>变化</th><th>临床意义（参考）</th></tr>
      %s
    </table>
  </div>

  <div class="section" id="period">
    <h3>四、周 / 月 / 季 / 年分析 · 点击模块切换</h3>
    <p style="font-size:13px;color:var(--mut)">周期 AHI = 周期内事件总数 / 周期内总小时数（加权，不是各夜 AHI 的简单平均）。近 7 天、近 30 天按最新一晚日期往前数；本月、本季、本年按日历。</p>
    <div class="ctl" id="periodBtns">
      <button class="mbtn on" data-p="近 7 天">周 · 近 7 天</button>
      <button class="mbtn" data-p="近 30 天">近 30 天</button>
      <button class="mbtn" data-p="本月">月 · 本月</button>
      <button class="mbtn" data-p="本季">季 · 本季</button>
      <button class="mbtn" data-p="本年">年 · 本年</button>
    </div>
    <div id="periodCard"></div>
  </div>
  </div>
  </div>

  <div class="section" id="nights">
    <h3>五、每夜总表 · 最新在前</h3>
    <table>
      <tr><th>日期</th><th>小时</th><th>AHI</th><th>阻塞/中央/低通气</th><th>漏气 95%%</th><th>95%% 压力</th><th>潮气量中位</th></tr>
      %s
    </table>
  </div>

  <div class="section" id="months">
    <h3>六、月度分析 · 使用夜口径</h3>
    <table>
      <tr><th>月份</th><th>夜数</th><th>总小时</th><th>周期 AHI</th><th>平均漏气 95%%</th></tr>
      %s
    </table>
  </div>

  <div class="section" id="checks">
    <h3>七、核对 · 每晚自动做</h3>
    <p style="font-size:14px">日历日 %d 天，其中使用夜 %d 夜、零使用日 %d 天；治疗均值只用使用夜算，零使用日不混入。血氧在卡上全为 -1，说明未接血氧仪，留空不填 0。</p>
  </div>

  <div class="note">
    <strong>说明：</strong>
    <ul>
      <li>本页只读卡，不写卡；历史存在输出目录的 <code>history.json</code> 里，下次插卡读到新夜时自动追加，同一日期新数据覆盖旧数据。</li>
      <li>AHI 一律按小时率；周期 AHI 为加权值；零使用日的 AHI / 漏气 / 压力 / 时长在卡上都是 0，不计入治疗均值。</li>
      <li>本报告数据源自 STR.edf 每日汇总，不含分钟波形；前日比较的“临床意义”列与本说明只作参考，不作诊断或调压建议，调压走睡眠医生。</li>
    </ul>
  </div>

  <footer>由 generate_airsense_report.py v1 生成 · 报告更新日期 %s · STR.edf %s</footer>
</div>
<script id="report-data" type="application/json">%s</script>
<script>
var REPORT = JSON.parse(document.getElementById("report-data").textContent);
var interpSel = document.getElementById("interpSel");
Object.keys(REPORT.interp).forEach(function(d){
  var o = document.createElement("option"); o.value = d; o.textContent = d; interpSel.appendChild(o);
});
interpSel.selectedIndex = interpSel.options.length - 1;
function showInterp(){
  var it = REPORT.interp[interpSel.value];
  if (!it) return;
  document.getElementById("interpTitle").textContent = it.title;
  document.getElementById("interpText").textContent = it.text;
}
interpSel.addEventListener("change", showInterp);
showInterp();
function fmtNum(v){ return v === null || v === undefined ? "—" : v; }
function showPeriod(label){
  var s = REPORT.periods[label];
  var card = document.getElementById("periodCard");
  if (!s){ card.innerHTML = "<p>该区间暂无数据。</p>"; return; }
  card.innerHTML = "<table><tr><th>区间</th><th>夜数</th><th>总小时</th><th>周期 AHI</th><th>平均时长</th><th>平均漏气 95</th><th>平均 95 压力</th></tr>"
    + "<tr><td>" + label + "</td><td>" + s.nights + "</td><td>" + s.hours + "</td><td>" + fmtNum(s.ahi)
    + "</td><td>" + fmtNum(s.avg_hours) + "</td><td>" + fmtNum(s.avg_leak95) + "</td><td>" + fmtNum(s.avg_press95) + "</td></tr></table>";
}
document.querySelectorAll("#periodBtns .mbtn").forEach(function(b){
  b.addEventListener("click", function(){
    document.querySelectorAll("#periodBtns .mbtn").forEach(function(x){ x.classList.remove("on"); });
    b.classList.add("on"); showPeriod(b.getAttribute("data-p"));
  });
});
showPeriod("近 7 天");
var METRICS = {ahi:["AHI","/小时","#2563eb"],leak95:["漏气 95","L/min","#dc2626"],press95:["95 压力","cmH2O","#0ea5e9"],dur:["使用时长","小时","#16a34a"]};
var curMetric = "ahi";
function drawChart(){
  var tr = REPORT.trend;
  var cv = document.getElementById("chart"), ctx = cv.getContext("2d");
  var info = document.getElementById("chartInfo");
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (!tr.dates.length){ info.textContent = "暂无趋势数据。"; return; }
  var L = 56, R = 16, T = 20, B = 34, W = cv.width - L - R, H = cv.height - T - B;
  var vals = tr[curMetric].filter(function(v){ return v !== null && v !== undefined; });
  var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  var pad = (hi - lo) * 0.15 + 0.5; lo -= pad; hi += pad;
  var n = tr.dates.length;
  function X(i){ return L + W * i / (n - 1 || 1); }
  function Y(v){ return T + H * (1 - (v - lo) / (hi - lo)); }
  ctx.strokeStyle = "#e2e8f0"; ctx.fillStyle = "#64748b"; ctx.font = "11px sans-serif"; ctx.lineWidth = 1;
  for (var g = 0; g <= 4; g++){
    var v = lo + (hi - lo) * g / 4, y = Y(v);
    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + W, y); ctx.stroke();
    ctx.fillText(v.toFixed(1), 6, y + 4);
  }
  var step = Math.max(1, Math.floor(n / 12));
  for (var i = 0; i < n; i += step){
    ctx.fillText(tr.dates[i].slice(5), X(i) - 14, T + H + 20);
  }
  ctx.strokeStyle = METRICS[curMetric][2]; ctx.lineWidth = 2; ctx.beginPath();
  var started = false;
  tr[curMetric].forEach(function(v, i){
    if (v === null || v === undefined){ started = false; return; }
    if (!started){ ctx.moveTo(X(i), Y(v)); started = true; } else { ctx.lineTo(X(i), Y(v)); }
  });
  ctx.stroke();
  info.textContent = METRICS[curMetric][0] + "（" + METRICS[curMetric][1] + "）· 共 " + n + " 个使用夜 · " + tr.dates[0] + " 至 " + tr.dates[n - 1];
  cv.onmousemove = function(ev){
    var rect = cv.getBoundingClientRect();
    var mx = (ev.clientX - rect.left) * cv.width / rect.width;
    var idx = Math.round((mx - L) / W * (n - 1));
    if (idx < 0 || idx >= n) return;
    var tip = document.getElementById("tip");
    tip.textContent = tr.dates[idx] + "  " + METRICS[curMetric][0] + " " + tr[curMetric][idx] + " " + METRICS[curMetric][1];
    tip.style.display = "block"; tip.style.left = (mx + 12) + "px"; tip.style.top = "8px";
  };
  cv.onmouseleave = function(){ document.getElementById("tip").style.display = "none"; };
}
document.querySelectorAll("#metricBtns .mbtn").forEach(function(b){
  b.addEventListener("click", function(){
    document.querySelectorAll("#metricBtns .mbtn").forEach(function(x){ x.classList.remove("on"); });
    b.classList.add("on"); curMetric = b.getAttribute("data-i"); drawChart();
  });
});
drawChart();
</script>
</body>
</html>""" % (
        generated, len(nights_sorted), calendar_days, latest["date"] if latest else "—",
        latest["date"] if latest else "—", fmt(latest["dur_hours"]) if latest else "—",
        fmt(latest["ahi"]) if latest else "—", fmt(latest["oai"]) if latest else "—",
        fmt(latest["cai"]) if latest else "—", fmt(latest["hi"]) if latest else "—",
        fmt(latest["leak95"]) if latest else "—", fmt(latest["press95"]) if latest else "—",
        mode_note, comp_summary, comp_rows, night_rows, month_rows,
        calendar_days, len(nights_sorted), zero_days, generated, "已读取",
        report_json)


def main():
    ap = argparse.ArgumentParser(description="AirSense 10 插卡即读完整报告生成器")
    ap.add_argument("--sd", default=None, help="卡目录、STR.edf 文件或卡副本根目录")
    ap.add_argument("--out", default=None, help="输出目录，默认与脚本同目录的 output")
    args = ap.parse_args()
    str_path = find_card(args.sd)
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out_dir, exist_ok=True)
    hist_path = os.path.join(out_dir, "history.json")
    history = {}
    if os.path.isfile(hist_path):
        try:
            history = json.load(open(hist_path, encoding="utf-8"))
        except Exception:
            history = {}
    edf = load_edf(str_path)
    days = build_days(edf)
    calendar_days = len(days)
    used = [to_night(r) for r in days if (r.get("dur") or 0) > 0]
    zero_days = calendar_days - len(used)
    for n in used:
        history[n["date"]] = n
    nights = [history[k] for k in sorted(history)]
    generated = datetime.datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    html = build_html(nights, calendar_days, zero_days, generated)
    html_path = os.path.join(out_dir, "airsense_report.html")
    open(html_path, "w", encoding="utf-8").write(html)
    json.dump(history, open(hist_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "nights.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["日期", "小时", "AHI", "阻塞", "中央", "低通气", "漏气中位", "漏气95%", "漏气最高", "压力中位", "95%压力", "潮气量中位", "呼吸频率中位"])
        for n in nights:
            w.writerow([n["date"], n["dur_hours"], n["ahi"], n["oai"], n["cai"], n["hi"],
                        n["leak"], n["leak95"], n["leakmax"], n["press"], n["press95"], n["tv"], n["rr"]])
    print("卡：%s" % str_path)
    print("日历日：%d，使用夜：%d，零使用日：%d" % (calendar_days, len(used), zero_days))
    print("历史夜数：%d" % len(nights))
    print("报告：%s" % html_path)
    print("历史：%s" % hist_path)
    if nights:
        print("最新一晚：%s，%s 小时，AHI %s" % (nights[-1]["date"], nights[-1]["dur_hours"], nights[-1]["ahi"]))


if __name__ == "__main__":
    main()
