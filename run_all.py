"""run_all.py —— 一键跑完三个需求。

    python run_all.py                              # 用默认的示例数据
    python run_all.py -i 报名表.csv -o 结果/        # 用自己的真实数据
    python run_all.py -i 报名表.csv --id-length 10  # 顺便校验学号必须是 10 位

它依次调用：
    需求1  src/overview.py   读入与概览
    需求2  src/validate.py   校验与清洗（问题清单）
    需求3  src/report.py     统计与导出（干净数据 + 汇总表）

产物统一落在 --output-dir 下，输入文件全程只读。
"""

from __future__ import annotations

import argparse
import os
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import common, overview, report, validate  # noqa: E402

DEFAULT_INPUT = os.path.join("data", "signup_raw.csv")
DEFAULT_OUTPUT = "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="招新报名数据清洗与统计：一键跑完概览 + 校验 + 统计",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT,
                        help=f"报名表 CSV，默认 {DEFAULT_INPUT}")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_OUTPUT,
                        help=f"输出目录，默认 {DEFAULT_OUTPUT}/")
    parser.add_argument("--id-length", type=int, default=validate.DEFAULT_ID_LENGTH,
                        help="学号期望位数，0 = 不校验（默认）")
    parser.add_argument("--strict-id-length", action="store_true",
                        help="学号位数不符时算错误（默认只算提示）")
    parser.add_argument("--choices", default="", help="部门清单，逗号分隔")
    parser.add_argument("--drop-all-duplicates", action="store_true",
                        help="重复报名全部剔除（默认保留第 1 次提交）")
    return parser


def main(argv=None) -> int:
    common.enable_utf8_output()
    args = build_parser().parse_args(argv)

    if not os.path.exists(args.input):
        print(f"[错误] 找不到输入文件：{args.input}\n"
              f"       如果是第一次跑，先执行：python tools/make_sample_data.py",
              file=sys.stderr)
        return 2

    os.makedirs(args.output_dir, exist_ok=True)
    started = time.time()
    departments = tuple(d.strip() for d in args.choices.split(",") if d.strip()) or None

    print(">>> 需求1/3：读入与概览")
    result = overview.analyze(args.input)
    overview_text = overview.render(result)
    print(overview_text)
    overview_path = common.write_text(os.path.join(args.output_dir, "概览报告.txt"), overview_text)
    print(f"概览报告已保存：{overview_path}\n")

    print(">>> 需求2/3：校验与清洗")
    _raw, columns, rows, _meta = common.read_csv_rows(args.input)
    digest_before = validate.file_digest(args.input)
    issues_by_line, dup_groups = validate.validate(
        rows, id_length=args.id_length, strict_id_length=args.strict_id_length,
        departments=departments or validate.DEFAULT_DEPARTMENTS)
    problem_rows = validate.build_problem_rows(rows, issues_by_line, columns)
    problem_detail = validate.build_problem_detail(rows, issues_by_line, columns)
    path_problem = common.write_csv(os.path.join(args.output_dir, "问题清单.csv"),
                                    validate.problem_headers(columns), problem_rows)
    path_detail = common.write_csv(os.path.join(args.output_dir, "问题清单_明细.csv"),
                                   validate.detail_headers(columns), problem_detail)
    digest_after = validate.file_digest(args.input)
    error_lines = [ln for ln, iss in issues_by_line.items()
                   if any(i.level == validate.LEVEL_ERROR for i in iss)]
    print(f"有问题的行：{len(problem_rows)} 行（错误级 {len(error_lines)} 行）")
    print(f"问题清单：{path_problem}")
    print(f"问题明细：{path_detail}")
    print(f"原文件未被修改：{'是' if digest_before == digest_after else '否（请检查！）'}\n")

    print(">>> 需求3/3：统计与导出")
    stats = report.run(args.input, args.output_dir, id_length=args.id_length,
                       strict_id_length=args.strict_id_length, departments=departments,
                       drop_all_duplicates=args.drop_all_duplicates)

    print("\n>>> 全部完成，产物清单：")
    artifacts = [("概览报告", overview_path)] + list(stats["output_paths"].items())  # type: ignore[arg-type]
    for label, out_path in artifacts:
        print(f"  {common.pad(label, 24)}{out_path}")
    print(f"\n耗时 {time.time() - started:.2f} 秒。输入文件始终未被修改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
