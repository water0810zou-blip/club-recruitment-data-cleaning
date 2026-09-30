"""report.py —— 需求 3：统计与导出。

做的事：
  · 按第一志愿分组统计人数，输出一张汇总表（CSV + Markdown 两种）
  · 统计两个志愿都填了的人有多少、只填一个的有多少
  · 把清洗后的干净数据导出成新 CSV

口径说明（重要，README 里有一模一样的表述）：
  · 统计一律基于「清洗后」的数据：含错误级问题的行先被剔除，
    重复报名只保留第 1 次提交。这样一张表里的每个人都是「可联系、可录用」的。
  · 提示级问题（例如两个志愿填成同一个）不算错误，仍计入统计，但会在问题清单里可查。
  · 想改用原始数据统计，加 --keep-problems 即可（会在报告里注明口径）。

命令行示例：
  python src/report.py --input data/signup_raw.csv --output-dir output
  python src/report.py -i data/signup_raw.csv --keep-problems       # 原始口径
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src import common, validate                   # type: ignore
else:
    from . import common, validate

LINE_COLUMN = "原始行号"      # 干净数据里额外加的溯源列


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------

def count_by_first_choice(rows: Sequence[Dict[str, str]]) -> List[Tuple[str, int, float]]:
    """按第一志愿分组统计人数，返回 [(志愿1, 人数, 占比)]，按人数降序、名称升序。"""
    counter = Counter(common.normalize(r.get("志愿1", "")) or "(未填写)" for r in rows)
    total = sum(counter.values())
    result = [(choice, cnt, (cnt / total if total else 0.0)) for choice, cnt in counter.items()]
    result.sort(key=lambda item: (-item[1], item[0]))
    return result


def count_choice_completeness(rows: Sequence[Dict[str, str]]) -> List[Tuple[str, int, float]]:
    """统计两个志愿的填写情况，返回 [(口径, 人数, 占比)]。

    分四类，互斥且加总等于总人数：
      · 两个志愿都填了
      · 只填了第一志愿
      · 只填了第二志愿
      · 两个都没填
    """
    both = only_first = only_second = neither = 0
    for row in rows:
        c1 = common.normalize(row.get("志愿1", ""))
        c2 = common.normalize(row.get("志愿2", ""))
        if c1 and c2:
            both += 1
        elif c1:
            only_first += 1
        elif c2:
            only_second += 1
        else:
            neither += 1
    total = len(rows)
    items = [("两个志愿都填了", both), ("只填了第一志愿", only_first),
             ("只填了第二志愿", only_second), ("两个志愿都没填", neither)]
    return [(label, cnt, (cnt / total if total else 0.0)) for label, cnt in items]


def count_second_choice(rows: Sequence[Dict[str, str]]) -> List[Tuple[str, int]]:
    """附加统计：第二志愿的热度（只在报告里作为参考，不影响主口径）。"""
    counter = Counter(common.normalize(r.get("志愿2", "")) for r in rows)
    counter.pop("", None)
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------

def build_clean_rows(rows: Sequence[Dict[str, str]], columns: Sequence[str]) -> List[Dict[str, object]]:
    """干净数据的导出结构：首列是原始行号（方便回查问卷），其余保持原字段顺序。"""
    fields = common.source_fields(columns)
    return [{LINE_COLUMN: row.get(common.LINE_KEY, ""),
             **{f: row.get(f, "") for f in fields}} for row in rows]


def render_table_md(title: str, headers: Sequence[str], body: Sequence[Sequence[object]],
                    aligns: Sequence[str]) -> str:
    """把统计结果渲染成 Markdown 表格，方便直接贴进会议纪要。"""
    sep = {"right": "---:", "left": ":---", "center": ":---:"}
    lines = [f"### {title}", "",
             "| " + " | ".join(str(h) for h in headers) + " |",
             "| " + " | ".join(sep.get(a, "---") for a in aligns) + " |"]
    for row in body:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------

def render_report(*, path: str, total_rows: int, clean_rows, dropped, dup_groups,
                  by_first, completeness, by_second, keep_problems: bool, output_paths: Dict[str, str],
                  departments: Sequence[str] = ()) -> str:
    lines: List[str] = []
    bar = "=" * 66
    total_clean = len(clean_rows)

    lines += [bar, "招新报名数据清洗与统计 · 需求 3：统计与导出", bar,
              f"输入文件 : {os.path.abspath(path)}",
              f"统计口径 : " + ("原始数据（含问题行，--keep-problems）" if keep_problems
                                else "清洗后数据（已剔除错误行、重复报名只留第 1 次）"),
              ""]

    lines.append("【一】数据前后对比")
    lines.append(f"  原始数据   : {total_rows} 行")
    lines.append(f"  剔除       : {len(dropped)} 行"
                 f"（重复报名的第 1 次提交会被保留，其余重复剔除）")
    lines.append(f"  参与统计   : {total_clean} 行")
    lines.append(f"  重复报名   : {len(dup_groups)} 个学号、"
                 f"{sum(len(v) for v in dup_groups.values())} 行提交")
    lines.append("")

    lines.append("【二】按第一志愿分组统计（汇总表）")
    lines.append("  " + common.pad("第一志愿", 14) + common.pad("人数", 8, "right")
                 + common.pad("占比", 10, "right") + "  " + "占比条形图")
    lines.append("  " + "-" * 62)
    max_cnt = max((cnt for _c, cnt, _p in by_first), default=1)
    for choice, cnt, ratio in by_first:
        bar_len = round(cnt / max_cnt * 16) if max_cnt else 0
        lines.append("  " + common.pad(choice, 14) + common.pad(cnt, 8, "right")
                     + common.pad(f"{ratio:.1%}", 10, "right") + "  " + "█" * bar_len)
    lines.append("  " + "-" * 62)
    lines.append("  " + common.pad("合计", 14) + common.pad(total_clean, 8, "right")
                 + common.pad("100.0%", 10, "right"))
    unknown_choices = [c for c, _n, _r in by_first if departments and c not in set(departments)]
    if unknown_choices:
        lines.append("")
        lines.append(f"  注：表中 {'、'.join(unknown_choices)} 不在部门清单内，"
                     f"已在问题清单里标为「提示」，建议人工确认归属后再并入正式分组。")
    lines.append("")

    lines.append("【三】两个志愿的填写情况")
    lines.append("  " + common.pad("情况", 20) + common.pad("人数", 8, "right")
                 + common.pad("占比", 10, "right"))
    lines.append("  " + "-" * 40)
    for label, cnt, ratio in completeness:
        lines.append("  " + common.pad(label, 20) + common.pad(cnt, 8, "right")
                     + common.pad(f"{ratio:.1%}", 10, "right"))
    lines.append("  " + "-" * 40)
    lines.append("  " + common.pad("合计", 20) + common.pad(total_clean, 8, "right")
                 + common.pad("100.0%", 10, "right"))
    both = next((cnt for label, cnt, _r in completeness if label == "两个志愿都填了"), 0)
    one = total_clean - both - next((cnt for label, cnt, _r in completeness
                                     if label == "两个志愿都没填"), 0)
    lines.append("")
    lines.append(f"  一句话回答需求：两个志愿都填了的有 {both} 人；"
                 f"只填了一个志愿的有 {one} 人。")
    lines.append("")

    if by_second:
        lines.append("【四】附加参考：第二志愿热度（仅统计填了第二志愿的人）")
        for choice, cnt in by_second:
            lines.append(f"  {common.pad(choice, 14)}{cnt} 人次")
        lines.append("")

    lines.append("【五】输出文件")
    for label, out_path in output_paths.items():
        lines.append(f"  {common.pad(label, 22)}{out_path}")
    lines.append(bar)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="需求 3：按第一志愿分组统计、双志愿填写情况统计，并导出清洗后的干净 CSV")
    parser.add_argument("--input", "-i", required=True, help="报名表 CSV，例如 data/signup_raw.csv")
    parser.add_argument("--output-dir", "-o", default="output", help="输出目录，默认 output/")
    parser.add_argument("--id-length", type=int, default=validate.DEFAULT_ID_LENGTH,
                        help="学号期望位数，0 表示不校验（默认）")
    parser.add_argument("--strict-id-length", action="store_true",
                        help="把学号位数不符升级为错误级")
    parser.add_argument("--choices", default="", help="部门清单，逗号分隔")
    parser.add_argument("--drop-all-duplicates", action="store_true",
                        help="重复报名全部剔除（默认保留第 1 次提交）")
    parser.add_argument("--keep-problems", action="store_true",
                        help="用原始数据统计（不剔除问题行），仅用于对比")
    return parser


def run(input_path: str, output_dir: str, *, id_length: int = validate.DEFAULT_ID_LENGTH,
        strict_id_length: bool = False, departments: Optional[Sequence[str]] = None,
        drop_all_duplicates: bool = False, keep_problems: bool = False,
        verbose: bool = True) -> Dict[str, object]:
    """跑完整的需求3 流程，返回统计结果与产物路径（供 run_all.py 与测试复用）。"""
    departments = tuple(departments) if departments else validate.DEFAULT_DEPARTMENTS
    _raw, columns, rows, _meta = common.read_csv_rows(input_path)

    missing, _unknown = common.check_required_columns(columns)
    if missing:
        raise common.DataFileError(f"输入文件缺少必填列：{', '.join(missing)}")

    issues_by_line, dup_groups = validate.validate(
        rows, id_length=id_length, strict_id_length=strict_id_length, departments=departments)
    clean_rows, dropped = validate.split_clean(rows, issues_by_line, dup_groups,
                                               drop_all_duplicates=drop_all_duplicates)
    stat_rows = rows if keep_problems else clean_rows

    by_first = count_by_first_choice(stat_rows)
    completeness = count_choice_completeness(stat_rows)
    by_second = count_second_choice(stat_rows)

    # ---- 汇总表：按第一志愿 ----
    summary_rows = [{"第一志愿": choice, "人数": cnt, "占比": f"{ratio:.2%}"}
                    for choice, cnt, ratio in by_first]
    summary_rows.append({"第一志愿": "合计", "人数": len(stat_rows), "占比": "100.00%"})
    summary_headers = ["第一志愿", "人数", "占比"]
    path_summary = common.write_csv(os.path.join(output_dir, "汇总表_按第一志愿.csv"),
                                    summary_headers, summary_rows)

    # ---- 汇总表：双志愿填写情况 ----
    complete_rows = [{"情况": label, "人数": cnt, "占比": f"{ratio:.2%}"}
                     for label, cnt, ratio in completeness]
    complete_rows.append({"情况": "合计", "人数": len(stat_rows), "占比": "100.00%"})
    complete_headers = ["情况", "人数", "占比"]
    path_complete = common.write_csv(os.path.join(output_dir, "汇总表_双志愿填写情况.csv"),
                                     complete_headers, complete_rows)

    # ---- Markdown 版汇总表（方便直接贴进纪要）----
    md = "# 招新报名统计汇总\n\n"
    md += f"- 数据来源：`{os.path.basename(input_path)}`\n"
    md += f"- 统计口径：{'原始数据（含问题行）' if keep_problems else '清洗后数据'}\n"
    md += f"- 参与统计人数：**{len(stat_rows)}**\n\n"
    md += render_table_md("按第一志愿分组",
                          summary_headers,
                          [[r["第一志愿"], r["人数"], r["占比"]] for r in summary_rows],
                          ["left", "right", "right"])
    md += "\n" + render_table_md("两个志愿的填写情况",
                                 complete_headers,
                                 [[r["情况"], r["人数"], r["占比"]] for r in complete_rows],
                                 ["left", "right", "right"])
    if by_second:
        md += "\n" + render_table_md("第二志愿热度（附加参考）", ["第二志愿", "人次"],
                                     [[c, n] for c, n in by_second], ["left", "right"])
    path_md = common.write_text(os.path.join(output_dir, "汇总表.md"), md)

    # ---- 清洗后的干净数据（无论统计用哪个口径，导出的都是清洗后的数据）----
    clean_export = build_clean_rows(clean_rows, columns)
    path_clean = common.write_csv(os.path.join(output_dir, "清洗后数据.csv"),
                                  [LINE_COLUMN] + common.source_fields(columns), clean_export)

    # ---- 被剔除的行，单独留一份，方便人工复核 ----
    dropped_export = [{"行号": int(r.get(common.LINE_KEY, 0)),
                       "剔除原因": "；".join(i.detail for i in iss if i.level == validate.LEVEL_ERROR),
                       **{f: r.get(f, "") for f in common.source_fields(columns)}}
                      for r, iss in dropped]
    path_dropped = common.write_csv(os.path.join(output_dir, "被剔除的行.csv"),
                                    ["行号", "剔除原因"] + common.source_fields(columns),
                                    dropped_export)

    output_paths = {
        "按第一志愿汇总表": path_summary,
        "双志愿填写情况汇总表": path_complete,
        "汇总表（Markdown）": path_md,
        "清洗后数据": path_clean,
        "被剔除的行（人工核对用）": path_dropped,
    }

    report = render_report(path=input_path, total_rows=len(rows), clean_rows=clean_rows,
                           dropped=dropped, dup_groups=dup_groups, by_first=by_first,
                           completeness=completeness, by_second=by_second,
                           keep_problems=keep_problems, output_paths=output_paths,
                           departments=departments)
    path_report = common.write_text(os.path.join(output_dir, "统计报告.txt"), report)
    if verbose:
        print(report)

    return {"rows": rows, "columns": columns, "clean_rows": clean_rows, "dropped": dropped,
            "dup_groups": dup_groups, "issues_by_line": issues_by_line,
            "by_first": by_first, "completeness": completeness, "by_second": by_second,
            "output_paths": output_paths, "report_path": path_report}


def main(argv: Optional[List[str]] = None) -> int:
    common.enable_utf8_output()
    args = build_parser().parse_args(argv)
    departments = tuple(d.strip() for d in args.choices.split(",") if d.strip())
    try:
        run(args.input, args.output_dir, id_length=args.id_length,
            strict_id_length=args.strict_id_length, departments=departments or None,
            drop_all_duplicates=args.drop_all_duplicates, keep_problems=args.keep_problems)
    except common.DataFileError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
