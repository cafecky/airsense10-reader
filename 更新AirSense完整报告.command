#!/bin/bash
# Double-click to run from any folder: use the script's own directory.
# 双击运行：自动切到本文件所在目录，放在哪个文件夹都能用。
cd "$(dirname "$0")" || { echo "找不到工作目录"; read -r _; exit 1; }
python3 generate_airsense_report.py
echo
echo "报告已生成在 output/airsense_report.html，正在打开…… / Report generated in output/airsense_report.html, opening..."
open output/airsense_report.html 2>/dev/null || echo "请手动打开 output/airsense_report.html"
echo
echo "按回车关闭窗口..."
read -r _
