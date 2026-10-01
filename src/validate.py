"""validate.py —— 需求 2：校验与清洗。

规则（照需求原文）：
  · 学号必须是纯数字
  · 邮箱必须是 学号@smbu.edu.cn（对不上就是填错了）
  · 找出重复报名（同一学号出现两次）
  · 不要直接改原文件：把有问题的行单独导出一份「问题清单」，并写明每行为什么被判为有问题

关于「有问题」的两种级别（重要设计约定）：
  · 错误：数据本身不可用，必须联系同学更正。清洗时会把这些行挡在干净数据之外。
  · 提示：可疑但不一定是错，交给人判断（例如两个志愿填成同一个部门）。
    提示级的行仍然算干净数据，只是会在清单里被标注出来，避免机器误杀。

命令行示例：
  python src/validate.py --input data/signup_raw.csv --output-dir output
  python src/validate.py -i data/signup_raw.csv --id-length 10        # 额外校验学号位数
  python src/validate.py -i data/signup_raw.csv --fail-on-error       # 有错误时退出码为 1
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src import common                            # type: ignore
else:
    from . import common

# --------------------------------------------------------------------------
# 规则常量
# --------------------------------------------------------------------------

EMAIL_DOMAIN = "smbu.edu.cn"          # 邮箱域名：学号@smbu.edu.cn
ID_PATTERN = re.compile(r"^[0-9]+$")  # 纯数字 = 全部是半角 0-9
NAME_PATTERN = re.compile(r"[0-9A-Za-z]")

# 协会现有部门（见 common.py 的 DEPARTMENT_CENTERS 组织结构）。
# 用于「志愿填了清单外的部门」这条提示级检查，可用 --choices 覆盖。
DEFAULT_DEPARTMENTS: Tuple[str, ...] = common.DEFAULT_DEPARTMENTS

DEFAULT_ID_LENGTH = 0        # 0 = 不校验学号位数（默认，见 README「假设」）

LEVEL_ERROR = "错误"
LEVEL_WARN = "提示"

# 问题的内部类型名 → 中文类别名（清单里给人看的）
CATEGORY_LABELS = {
    "required_blank": "必填项为空",
    "id_format": "学号格式",
    "id_length": "学号位数",
    "email_format": "邮箱格式",
    "email_mismatch": "邮箱与学号不匹配",
    "duplicate": "重复报名",
    "choice_same": "两个志愿填成同一个",
    "choice_unknown": "志愿不在部门清单内",
    "name_suspect": "姓名疑似异常",
}


@dataclass(frozen=True)
class Issue:
    """一条问题记录：哪一行、哪一列、什么问题、多严重、为什么。"""

    line_no: int          # 文件中的物理行号（表头 = 第 1 行）
    category: str         # 内部类型名，见 CATEGORY_LABELS
    level: str            # 错误 / 提示
    field: str            # 涉及字段
    detail: str           # 人话说明：为什么这行被判为有问题

    @property
    def label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def file_digest(path: str) -> str:
    """算文件 sha256，用来证明「跑完之后原文件一个字节都没变」。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_pure_digits(value: str) -> bool:
    """是否纯数字。

    注意 Python 的 str.isdigit() 对全角「２０２３」也返回 True，
    而问卷导出里全角数字是常见坑，所以这里用正则只认半角 0-9。
    """
    return bool(ID_PATTERN.match(value))


def split_email(email: str) -> Tuple[str, str, bool]:
    """拆邮箱，返回 (前缀, 域名, 是否格式合规)。"""
    if email.count("@") != 1:
        return "", "", False
    local, _, domain = email.partition("@")
    if not local or not domain or " " in email or not email.isascii():
        return local, domain, False
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return local, domain, False
    return local, domain, True


# --------------------------------------------------------------------------
# 逐行校验
# --------------------------------------------------------------------------

def check_single_row(row: Dict[str, str], line_no: int, *,
                     id_length: int = DEFAULT_ID_LENGTH,
                     strict_id_length: bool = False,
                     departments: Sequence[str] = DEFAULT_DEPARTMENTS) -> List[Issue]:
    """对一行做全部单行检查（不涉及跨行比较的重复报名）。"""
    issues: List[Issue] = []
    name = common.normalize(row.get("姓名", ""))
    sid = common.normalize(row.get("学号", ""))
    email = common.normalize(row.get("邮箱", ""))
    c1 = common.normalize(row.get("志愿1", ""))
    c2 = common.normalize(row.get("志愿2", ""))

    def add(category, level, field, detail):
        issues.append(Issue(line_no, category, level, field, detail))

    # ---- 1. 必填项为空 ---------------------------------------------------
    for field, value in (("姓名", name), ("学号", sid), ("邮箱", email), ("志愿1", c1)):
        if not value:
            add("required_blank", LEVEL_ERROR, field,
                f"{field}为空（{field}是必填项）")

    # ---- 2. 学号必须是纯数字 --------------------------------------------
    sid_ok = False
    if sid:
        if is_pure_digits(sid):
            sid_ok = True
            if id_length and len(sid) != id_length:
                add("id_length",
                    LEVEL_ERROR if strict_id_length else LEVEL_WARN, "学号",
                    f"学号 {sid} 是 {len(sid)} 位，与假设的 {id_length} 位不符"
                    f"（如需按本会惯例校验，请确认 --id-length）")
        else:
            hint = ""
            if any("０" <= ch <= "９" for ch in sid):
                hint = "；其中包含全角数字，请改回半角"
            elif " " in sid:
                hint = "；中间夹了空格"
            elif "." in sid:
                hint = "；像是从 Excel 带出来的 .0 尾巴"
            add("id_format", LEVEL_ERROR, "学号",
                f"学号「{sid}」不是纯数字{hint}")

    # ---- 3. 邮箱必须是 学号@smbu.edu.cn ---------------------------------
    if email:
        local, domain, well_formed = split_email(email)
        if not well_formed:
            add("email_format", LEVEL_ERROR, "邮箱",
                f"邮箱「{email}」格式不合法（应形如 学号@{EMAIL_DOMAIN}，"
                f"且不能含空格或多个 @）")
        elif domain.lower() != EMAIL_DOMAIN:
            if domain.lower().endswith("." + EMAIL_DOMAIN):
                why = f"多了子域名（应为 {EMAIL_DOMAIN}）"
            else:
                why = f"域名写错了（应为 {EMAIL_DOMAIN}）"
            add("email_mismatch", LEVEL_ERROR, "邮箱",
                f"邮箱域名对不上：实际是 {domain}，{why}")
        elif sid and sid_ok and local.lower() != sid.lower():
            add("email_mismatch", LEVEL_ERROR, "邮箱",
                f"邮箱与学号对不上：邮箱前缀是「{local}」，与学号「{sid}」不一致。"
                f"要求是 {sid}@{EMAIL_DOMAIN}")
        # 学号本身不合法（或为空）时只报学号那一处错误，邮箱不再重复扣分

    # ---- 4. 志愿相关（都是提示级，人工确认即可）-------------------------
    if c1 and c2 and c1 == c2:
        add("choice_same", LEVEL_WARN, "志愿2",
            f"志愿1 与志愿2 都填了「{c1}」，等于只填了一个志愿，建议与本人确认")
    known = set(departments)
    for field, value in (("志愿1", c1), ("志愿2", c2)):
        if value and value not in known:
            add("choice_unknown", LEVEL_WARN, field,
                f"{field}「{value}」不在部门清单（{', '.join(departments)}）里，"
                f"可能是新增部门或填错了")
    if name and NAME_PATTERN.search(name):
        add("name_suspect", LEVEL_WARN, "姓名",
            f"姓名「{name}」里混入了数字或英文字母，疑似填错字段")

    return issues


# --------------------------------------------------------------------------
# 跨行校验 + 汇总
# --------------------------------------------------------------------------

def find_duplicate_signups(rows: Sequence[Dict[str, str]]) -> Dict[str, List[int]]:
    """找出重复报名：同一个学号出现多次。

    学号为空的行不参与判断（空值属于「必填项为空」，不该再报一次重复）。
    返回 {学号: [行号, ...]}，只保留出现 ≥2 次、且按行号升序排列的组。
    """
    buckets: Dict[str, List[int]] = defaultdict(list)
    for row in rows:
        sid = common.normalize(row.get("学号", ""))
        if sid:
            buckets[sid].append(int(row.get(common.LINE_KEY, 0)))
    return {sid: sorted(lines) for sid, lines in buckets.items() if len(lines) > 1}


def validate(rows: Sequence[Dict[str, str]], *, id_length: int = DEFAULT_ID_LENGTH,
             strict_id_length: bool = False,
             departments: Sequence[str] = DEFAULT_DEPARTMENTS
             ) -> Tuple[Dict[int, List[Issue]], Dict[str, List[int]]]:
    """校验全部数据，返回 (按行号索引的问题列表, 重复报名分组)。"""
    by_line: Dict[int, List[Issue]] = defaultdict(list)
    for row in rows:
        line_no = int(row.get(common.LINE_KEY, 0))
        for issue in check_single_row(row, line_no, id_length=id_length,
                                      strict_id_length=strict_id_length,
                                      departments=departments):
            by_line[line_no].append(issue)

    dup_groups = find_duplicate_signups(rows)
    for sid, lines in dup_groups.items():
        for order, line_no in enumerate(lines, start=1):
            others = "、".join(f"第 {n} 行" for n in lines if n != line_no)
            by_line[line_no].append(Issue(
                line_no, "duplicate", LEVEL_ERROR, "学号",
                f"重复报名：学号 {sid} 共出现 {len(lines)} 次（{others}），"
                f"本条是第 {order} 次出现"))

    return dict(by_line), dup_groups


def row_has_error(issues: Iterable[Issue]) -> bool:
    return any(i.level == LEVEL_ERROR for i in issues)


def split_clean(rows: Sequence[Dict[str, str]], issues_by_line: Dict[int, List[Issue]],
                dup_groups: Dict[str, List[int]], *, drop_all_duplicates: bool = False
                ) -> Tuple[List[Dict[str, str]], List[Tuple[Dict[str, str], List[Issue]]]]:
    """把数据分成「干净可用」和「被剔除」两部分。

    剔除策略（可在 README 里看到同样的表述）：
      · 只要含「错误」级问题就剔除；
      · 但重复报名是特殊情形：同一学号提交了多次，人只可能来一次，
        所以默认保留第 1 次提交、剔除后面的重复；
        加 --drop-all-duplicates 则连第 1 次也剔除（更保守，适合人工再核）。
    """
    first_of_dup = {sid: lines[0] for sid, lines in dup_groups.items()}
    clean: List[Dict[str, str]] = []
    dropped: List[Tuple[Dict[str, str], List[Issue]]] = []

    for row in rows:
        line_no = int(row.get(common.LINE_KEY, 0))
        issues = issues_by_line.get(line_no, [])
        errors = [i for i in issues if i.level == LEVEL_ERROR]
        if not errors:
            clean.append(row)
            continue

        only_dup = all(i.category == "duplicate" for i in errors)
        sid = common.normalize(row.get("学号", ""))
        if only_dup and not drop_all_duplicates and first_of_dup.get(sid) == line_no:
            clean.append(row)          # 重复报名的第 1 次，保留
        else:
            dropped.append((row, issues))

    return clean, dropped


# --------------------------------------------------------------------------
# 导出问题清单
# --------------------------------------------------------------------------

def build_problem_rows(rows, issues_by_line, columns) -> List[Dict[str, object]]:
    """问题清单：一行对应一条有问题的原始记录，并写明为什么。"""
    fields = common.source_fields(columns)
    out: List[Dict[str, object]] = []
    for row in rows:
        line_no = int(row.get(common.LINE_KEY, 0))
        issues = issues_by_line.get(line_no, [])
        if not issues:
            continue
        levels = sorted({i.level for i in issues}, key=lambda x: 0 if x == LEVEL_ERROR else 1)
        out.append({
            "行号": line_no,
            "问题级别": "、".join(levels),
            "问题数": len(issues),
            "问题说明": "；".join(f"[{i.level}] {i.detail}" for i in issues),
            **{f: row.get(f, "") for f in fields},
        })
    out.sort(key=lambda r: (0 if str(r["问题级别"]).startswith(LEVEL_ERROR) else 1, int(r["行号"])))
    return out


def build_problem_detail(rows, issues_by_line, columns) -> List[Dict[str, object]]:
    """问题明细：一行对应一个具体问题，便于按类型筛选。"""
    fields = common.source_fields(columns)
    out: List[Dict[str, object]] = []
    for row in rows:
        line_no = int(row.get(common.LINE_KEY, 0))
        for issue in issues_by_line.get(line_no, []):
            out.append({
                "行号": line_no,
                "问题级别": issue.level,
                "问题类型": issue.label,
                "涉及字段": issue.field,
                "具体说明": issue.detail,
                **{f: row.get(f, "") for f in fields},
            })
    out.sort(key=lambda r: (0 if r["问题级别"] == LEVEL_ERROR else 1, int(r["行号"])))
    return out


PROBLEM_BASE_HEADERS = ["行号", "问题级别", "问题数", "问题说明"]
DETAIL_BASE_HEADERS = ["行号", "问题级别", "问题类型", "涉及字段", "具体说明"]


def problem_headers(columns: Sequence[str]) -> List[str]:
    """问题清单的表头：固定说明列 + 原始业务列（顺序与原表一致）。"""
    return PROBLEM_BASE_HEADERS + common.source_fields(columns)


def detail_headers(columns: Sequence[str]) -> List[str]:
    """问题明细的表头：固定说明列 + 原始业务列。"""
    return DETAIL_BASE_HEADERS + common.source_fields(columns)


# --------------------------------------------------------------------------
# 报告输出
# --------------------------------------------------------------------------

def render_summary(rows, issues_by_line, dup_groups, *, path, digest_before, digest_after,
                   id_length) -> str:
    total = len(rows)
    problem_lines = [ln for ln, iss in issues_by_line.items() if iss]
    error_lines = [ln for ln, iss in issues_by_line.items() if row_has_error(iss)]
    warn_only = [ln for ln in problem_lines if ln not in set(error_lines)]
    all_issues = [i for iss in issues_by_line.values() for i in iss]

    lines = ["=" * 66,
             "招新报名数据清洗与统计 · 需求 2：校验与清洗",
             "=" * 66,
             f"输入文件 : {os.path.abspath(path)}",
             f"检查行数 : {total}",
             f"学号位数校验 : " + (f"开启（按 {id_length} 位）" if id_length else "未开启（--id-length 0，见 README 假设）"),
             "",
             "【一】体检结果",
             f"  有问题的行   : {len(problem_lines)} 行"
             f"（其中错误级 {len(error_lines)} 行、仅提示级 {len(warn_only)} 行）",
             f"  问题条目总数 : {len(all_issues)} 条"
             f"（错误 {sum(1 for i in all_issues if i.level == LEVEL_ERROR)} 条、"
             f"提示 {sum(1 for i in all_issues if i.level == LEVEL_WARN)} 条）",
             f"  重复报名的学号 : {len(dup_groups)} 个，"
             f"涉及 {sum(len(v) for v in dup_groups.values())} 行",
             ""]

    lines.append("【二】按类型统计")
    if all_issues:
        counts = Counter((i.label, i.level) for i in all_issues)
        lines.append("  " + common.pad("问题类型", 20) + common.pad("级别", 6)
                     + common.pad("条目数", 8, "right"))
        lines.append("  " + "-" * 38)
        for (label, level), cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append("  " + common.pad(label, 20) + common.pad(level, 6)
                         + common.pad(cnt, 8, "right"))
    else:
        lines.append("  未发现任何问题")
    lines.append("")

    lines.append("【三】原文件保护")
    if digest_before == digest_after:
        lines.append(f"  [ok] 输入文件未被修改（sha256 前后一致：{digest_before[:16]}…）")
    else:
        lines.append("  [x] 警告：输入文件发生了变化，请检查是否有其他程序在写它")
    lines.append("  说明：本工具只以只读方式打开输入文件，所有结果都写到 --output-dir 下。")
    lines.append("")

    if dup_groups:
        lines.append("【四】重复报名明细（前 10 个学号）")
        for sid, ln in list(dup_groups.items())[:10]:
            lines.append(f"  学号 {sid}：出现 {len(ln)} 次，行号 {', '.join(map(str, ln))}")
        if len(dup_groups) > 10:
            lines.append(f"  ……（其余 {len(dup_groups) - 10} 个见问题清单）")
        lines.append("")

    lines.append("=" * 66)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="需求 2：校验与清洗 —— 学号纯数字、邮箱必须是 学号@smbu.edu.cn、"
                    "找出重复报名，并导出问题清单（不修改原文件）")
    parser.add_argument("--input", "-i", required=True, help="报名表 CSV，例如 data/signup_raw.csv")
    parser.add_argument("--output-dir", "-o", default="output", help="输出目录，默认 output/")
    parser.add_argument("--id-length", type=int, default=DEFAULT_ID_LENGTH,
                        help="学号期望位数，0 表示不校验（默认）。例如 --id-length 10")
    parser.add_argument("--strict-id-length", action="store_true",
                        help="把学号位数不符升级为「错误」级（默认只是提示）")
    parser.add_argument("--choices", default="", help="部门清单，用逗号分隔；默认用内置的 8 个部门")
    parser.add_argument("--fail-on-error", action="store_true",
                        help="存在错误级问题时退出码为 1，方便放进 CI / 批量脚本")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    common.enable_utf8_output()
    args = build_parser().parse_args(argv)
    departments = tuple(d.strip() for d in args.choices.split(",") if d.strip()) or DEFAULT_DEPARTMENTS

    try:
        digest_before = file_digest(args.input)
        _raw, columns, rows, _meta = common.read_csv_rows(args.input)
    except common.DataFileError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    missing, _unknown = common.check_required_columns(columns)
    if missing:
        print(f"[错误] 输入文件缺少必填列：{', '.join(missing)}", file=sys.stderr)
        return 2

    issues_by_line, dup_groups = validate(rows, id_length=args.id_length,
                                          strict_id_length=args.strict_id_length,
                                          departments=departments)
    clean_rows, dropped = split_clean(rows, issues_by_line, dup_groups)

    problem_rows = build_problem_rows(rows, issues_by_line, columns)
    problem_detail = build_problem_detail(rows, issues_by_line, columns)

    out_dir = args.output_dir
    path_rows = common.write_csv(os.path.join(out_dir, "问题清单.csv"),
                                 problem_headers(columns), problem_rows)
    path_detail = common.write_csv(os.path.join(out_dir, "问题清单_明细.csv"),
                                   detail_headers(columns), problem_detail)

    digest_after = file_digest(args.input)
    report = render_summary(rows, issues_by_line, dup_groups, path=args.input,
                            digest_before=digest_before, digest_after=digest_after,
                            id_length=args.id_length)
    print(report)
    print(f"问题清单（按行）: {path_rows}")
    print(f"问题清单（明细）: {path_detail}")
    print(f"干净数据行数    : {len(clean_rows)} 行；被剔除 {len(dropped)} 行"
          f"（清洗后 CSV 交给需求 3 导出）")

    if args.fail_on_error and len(problem_rows) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
