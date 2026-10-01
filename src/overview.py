"""overview.py —— 需求 1：读入与概览。

功能：
  · 读入问卷导出的报名 CSV（字段：姓名、学号、邮箱、志愿1、志愿2、推荐人）
  · 打印概览：一共多少行、每列有多少个空值、有没有完全重复的行

本脚本只读不写（除非显式指定 --save 输出报告文本）。

命令行示例：
  python src/overview.py --input data/signup_raw.csv
  python src/overview.py --input data/signup_raw.csv --save output/overview_report.txt
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

if __package__ in (None, ""):                      # 允许直接 python src/overview.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src import common                          # type: ignore
else:
    from . import common


# --------------------------------------------------------------------------
# 核心分析
# --------------------------------------------------------------------------

def count_blanks(rows: Sequence[Dict[str, str]], columns: Sequence[str]) -> List[Tuple[str, int]]:
    """统计每列的空值个数，返回 [(列名, 空值数)]，保持列顺序。"""
    return [(col, sum(1 for row in rows if not common.normalize(row.get(col, ""))))
            for col in columns]


def find_duplicate_rows(rows: Sequence[Dict[str, str]], columns: Sequence[str]) -> List[List[int]]:
    """找出「完全重复的行」：所有字段逐字相同。

    返回分组后的行号列表：[[12, 48], [77, 103, 104]]，按首次出现位置排序。
    注意：这里只按「完全相同」判断，和需求 2 的「同学号重复报名」是两回事。
    """
    buckets: Dict[Tuple[str, ...], List[int]] = defaultdict(list)
    for row in rows:
        key = tuple(common.normalize(row.get(col, "")) for col in columns)
        buckets[key].append(int(row.get(common.LINE_KEY, 0)))
    groups = [lines for lines in buckets.values() if len(lines) > 1]
    groups.sort(key=lambda lines: lines[0])
    return groups


def analyze(path: str) -> Dict[str, object]:
    """读入并分析，返回可直接打印/断言的结构化结果。"""
    raw_headers, columns, rows, meta = common.read_csv_rows(path)
    missing, unknown = common.check_required_columns(columns)
    blanks = count_blanks(rows, columns)
    dup_groups = find_duplicate_rows(rows, columns)
    total = len(rows) or 1     # 防止除零
    blank_any = sum(1 for row in rows if any(not common.normalize(row.get(c, "")) for c in columns))
    blank_required = sum(1 for row in rows
                         if any(not common.normalize(row.get(c, "")) for c in common.REQUIRED_COLUMNS
                                if c in columns))
    return {
        "path": os.path.abspath(path),
        "raw_headers": raw_headers,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "meta": meta,
        "blanks": blanks,
        "blank_rows": blank_any,
        "blank_required_rows": blank_required,
        "dup_groups": dup_groups,
        "dup_rows": sum(len(g) for g in dup_groups),
        "missing_required": missing,
        "unknown_columns": unknown,
        "blank_rate": {col: cnt / total for col, cnt in blanks},
    }


# --------------------------------------------------------------------------
# 打印
# --------------------------------------------------------------------------

BAR = "=" * 66


def render(result: Dict[str, object]) -> str:
    """把分析结果渲染成人可读的文本报告。"""
    lines: List[str] = []
    columns: List[str] = result["columns"]          # type: ignore[assignment]
    blanks: List[Tuple[str, int]] = result["blanks"]  # type: ignore[assignment]
    row_count: int = result["row_count"]            # type: ignore[assignment]
    meta: Dict[str, int] = result["meta"]           # type: ignore[assignment]
    dup_groups: List[List[int]] = result["dup_groups"]  # type: ignore[assignment]

    lines.append(BAR)
    lines.append("招新报名数据清洗与统计 · 需求 1：读入与概览")
    lines.append(BAR)
    lines.append(f"输入文件   : {result['path']}")
    lines.append(f"文件编码   : {meta['encoding']}")
    lines.append(f"统计时间   : {datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append("")

    lines.append("【一】规模概览")
    lines.append(f"  数据行数（不含表头） : {row_count}")
    lines.append(f"  列数                 : {len(columns)}")
    lines.append(f"  文件中总行数         : {meta['total_lines']}")
    lines.append(f"  跳过的完全空行       : {meta['blank_lines']}")
    lines.append(f"  必填项有缺失的行     : {result['blank_required_rows']}")
    lines.append(f"  含任意空值的行       : {result['blank_rows']}（含志愿2/推荐人这类选填项）")
    lines.append(f"  表头（原始）         : {', '.join(result['raw_headers'])}")  # type: ignore[arg-type]
    lines.append(f"  表头（归一后）       : {', '.join(columns)}")
    lines.append("")

    lines.append("【二】每列空值统计（空值 = 去掉首尾空格后为空）")
    name_w, cnt_w = 12, 8
    lines.append("  " + common.pad("列名", name_w) + common.pad("空值数", cnt_w, "right")
                 + common.pad("空值率", cnt_w, "right") + "  说明")
    lines.append("  " + "-" * 52)
    for col, cnt in blanks:
        rate = cnt / (row_count or 1)
        if col in common.REQUIRED_COLUMNS:
            note = "必填字段，空值算问题"
        else:
            note = "选填字段，空值不算问题"
        lines.append("  " + common.pad(col, name_w) + common.pad(cnt, cnt_w, "right")
                     + common.pad(f"{rate:.1%}", cnt_w, "right") + "  " + note)
    lines.append("  " + "-" * 52)
    lines.append("  " + common.pad(f"共 {row_count} 行 × {len(columns)} 列", name_w + 2 * cnt_w))
    lines.append("")

    lines.append("【三】完全重复的行（所有字段逐字相同）")
    if dup_groups:
        lines.append(f"  重复组数 : {len(dup_groups)} 组，共涉及 {result['dup_rows']} 行")
        for idx, group in enumerate(dup_groups[:5], start=1):
            lines.append(f"    第 {idx} 组：行号 {', '.join(str(n) for n in group)}")
        if len(dup_groups) > 5:
            lines.append(f"    ……（其余 {len(dup_groups) - 5} 组见导出的报告文件）")
    else:
        lines.append("  未发现完全重复的行")
    lines.append("")

    lines.append("【四】列名校对")
    missing = result["missing_required"]           # type: ignore[assignment]
    unknown = result["unknown_columns"]            # type: ignore[assignment]
    if missing:
        lines.append(f"  [x] 缺少必填列：{', '.join(missing)} —— 后续校验会跳过这些列的检查")
    else:
        lines.append("  [ok] 必填列齐全：姓名、学号、邮箱、志愿1")
    lines.append(f"  [{'!' if unknown else 'ok'}] 选填列：志愿2、推荐人"
                 + (f"；另有未识别列：{', '.join(unknown)}" if unknown else "（均已识别）"))
    lines.append("")
    lines.append("提示：本步骤只做体检，不修改任何数据；清洗与判定见需求 2（validate.py）。")
    lines.append(BAR)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="需求 1：读入报名 CSV 并打印概览（行数 / 每列空值 / 完全重复行）")
    parser.add_argument("--input", "-i", required=True, help="报名表 CSV 路径，例如 data/signup_raw.csv")
    parser.add_argument("--save", "-s", default=None, help="额外把报告保存为文本文件，例如 output/overview_report.txt")
    return parser


def main(argv: List[str] | None = None) -> int:
    common.enable_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        result = analyze(args.input)
    except common.DataFileError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    report = render(result)
    print(report)
    if args.save:
        print(f"\n报告已保存到：{common.write_text(args.save, report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
