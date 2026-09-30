"""make_sample_data.py —— 生成用于演示/自测的示例报名数据（合成数据，不含任何真实个人信息）。

为什么需要它：
  工具要能「跑起来」，就必须有一份带问题的输入。真实报名表不能公开，
  所以这里按固定随机种子（SEED）合成一份几百行的 CSV，并定向埋入
  学号非纯数字、邮箱与学号对不上、重复报名、空值等情况。

可控性：
  同一个种子每次生成的结果完全一致 —— 出问题能复现，测试也能写死期望值。

用法：
  python tools/make_sample_data.py                     # 输出 data/signup_raw.csv
  python tools/make_sample_data.py --rows 500
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from collections import Counter

SEED = 20260930

SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
                "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳")
GIVEN = ["子涵", "雨桐", "浩然", "思远", "嘉怡", "文博", "诗雨", "晨曦", "一鸣", "语彤",
         "俊杰", "佳琪", "鹤鸣", "若晨", "泽宇", "欣怡", "明轩", "雅雯", "致远", "雪瑶",
         "天宇", "静宜", "亦航", "舒予", "新宇", "梦琪", "书航", "婉清", "清越", "奕辰"]

# 协会现有的部门（用于识别「志愿填了不存在的部门」）
DEPARTMENTS = ["技术部", "宣传部", "外联部", "组织部", "文艺部", "体育部", "秘书处", "实践部"]

COLUMNS = ["姓名", "学号", "邮箱", "志愿1", "志愿2", "推荐人"]

OUT_DEFAULT = os.path.join("data", "signup_raw.csv")
NOTES_DEFAULT = os.path.join("data", "sample_data_notes.md")
EXPECT_DEFAULT = os.path.join("tests", "expected_sample_counts.json")

# 哪些类别属于「错误级」（行会被挡在干净数据之外）
ERROR_CATEGORIES = ["学号非纯数字", "邮箱与学号不匹配", "必填项为空", "重复报名"]


def make_name(rng: random.Random, used: set) -> str:
    while True:
        name = rng.choice(SURNAMES) + rng.choice(GIVEN)
        if name not in used:
            used.add(name)
            return name


def make_sid(rng: random.Random, seq: int) -> str:
    """10 位学号：4 位入学年份 + 6 位序号（这是示例数据的假设，见 README）。"""
    return f"{rng.choice(['2023', '2024', '2025'])}{seq:06d}"


def build_rows(rng: random.Random, clean_target: int, notes: dict):
    """返回 [(类别, 行 dict)]，类别用于统计「埋了多少坑」。"""
    rows = []
    used_names: set = set()
    seq = 0

    def new_row(name=None, sid=None, email=None, c1=None, c2=None, ref=None):
        nonlocal seq
        seq += 1
        sid = make_sid(rng, seq) if sid is None else sid
        name = make_name(rng, used_names) if name is None else name
        email = f"{sid}@smbu.edu.cn" if email is None else email
        c1 = rng.choice(DEPARTMENTS) if c1 is None else c1
        if c2 is None:
            others = [d for d in DEPARTMENTS if d != c1]
            c2 = rng.choice(others) if rng.random() < 0.45 else ""
        if ref is None and rng.random() < 0.35:
            ref = rng.choice(SURNAMES) + rng.choice(GIVEN)   # 随机「老成员」名字
        return {"姓名": name, "学号": sid, "邮箱": email,
                "志愿1": c1, "志愿2": c2, "推荐人": ref or ""}

    def add(category: str, row: dict):
        rows.append((category, row))
        notes.setdefault("injected", {})
        notes["injected"][category] = notes["injected"].get(category, 0) + 1

    # ---- 1. 正常数据 ----------------------------------------------------
    for _ in range(clean_target):
        add("正常", new_row())

    # ---- 2. 邮箱域名写成大写（看着可疑，其实应该放过）------------------
    ok_row = new_row()
    ok_row["邮箱"] = ok_row["邮箱"].upper()
    add("邮箱域名大写（应视为正常）", ok_row)

    # ---- 3. 学号不是纯数字 ---------------------------------------------
    for bad_sid in ["2023A01234", "２０２３０１０１２３", "2023 010123",
                    "2023-010123", "2023010123.0", "学号2023010123"]:
        add("学号非纯数字", new_row(sid=bad_sid, email=f"{bad_sid}@smbu.edu.cn"))

    # ---- 4. 邮箱与学号对不上 -------------------------------------------
    for sid, email in [
        ("2023010188", "2023010189@smbu.edu.cn"),     # 邮箱里是别人的学号
        ("2023010190", "2023010190@smbu.edu.com"),    # 域名写成 edu.com
        ("2023010191", "woshi_xiaoming@qq.com"),      # 私人 QQ 邮箱
        ("2023010192", "2023010192@stu.smbu.edu.cn"),  # 多了 stu. 子域名
        ("2023010193", "liuyang@smbu.edu.cn"),        # 姓名拼音，不是学号
        ("2023010194", "2023010194@@smbu.edu.cn"),    # 多打了一个 @
        ("2023010195", "20230101@smbu.edu.cn"),       # 邮箱里学号位数不对
    ]:
        add("邮箱与学号不匹配", new_row(sid=sid, email=email))

    # ---- 5. 必填项为空 --------------------------------------------------
    for _ in range(2):
        add("必填项为空", new_row(name=""))            # 姓名空
    for _ in range(2):
        add("必填项为空", new_row(sid="", email=""))    # 学号空
    add("必填项为空", new_row(email=""))               # 邮箱空
    for _ in range(3):
        add("必填项为空", new_row(c1=""))               # 志愿1 空

    # ---- 6. 重复报名（同一学号出现多次）--------------------------------
    dup_plan = [
        ("2023010201", True),    # 完全相同的两次提交（手抖提交了两遍）
        ("2023010202", False),   # 同学号但姓名不同（很可能学号填错）
        ("2023010203", False),   # 同学号、两次志愿不同（改志愿后重新提交）
    ]
    for sid, identical in dup_plan:
        base = new_row(sid=sid)
        add("重复报名", base)
        if identical:
            add("重复报名", dict(base))          # 逐字相同
        else:
            second = new_row(sid=sid)
            second["志愿1"] = rng.choice(DEPARTMENTS)
            add("重复报名", second)

    triple = new_row(sid="2023010204")
    add("重复报名", triple)
    add("重复报名", dict(triple))                # 三连提交，其中两条一模一样
    add("重复报名", new_row(sid="2023010204"))

    # ---- 7. 志愿 1 和志愿 2 填成同一个部门（提示级，不算错）------------
    for _ in range(4):
        row = new_row()
        row["志愿2"] = row["志愿1"]
        add("两个志愿填成同一个", row)

    # ---- 8. 志愿填了清单以外的部门（提示级）----------------------------
    for weird in ["电竞部", "食堂部", "技术部-宣传组"]:
        add("志愿不在部门清单内", new_row(c1=weird))

    # ---- 9. 姓名里混了数字（提示级）------------------------------------
    for bad_name in ["李四2", "王五3"]:
        add("姓名疑似异常", new_row(name=bad_name))

    # 期望值：完全重复行（所有字段逐字相同）用另一种方式独立算一遍
    counter = Counter(tuple(row[col] for col in COLUMNS) for _c, row in rows)
    identical_groups = [key for key, n in counter.items() if n > 1]
    notes["identical_dup_groups"] = len(identical_groups)
    notes["identical_dup_rows"] = sum(counter[key] for key in identical_groups)

    # 期望值：重复报名涉及多少行、分成几组
    dup_counter = Counter(row["学号"] for cat, row in rows if cat == "重复报名" and row["学号"])
    notes["dup_flagged_rows"] = sum(dup_counter.values())
    notes["dup_groups"] = len(dup_counter)

    rng.shuffle(rows)
    return rows


def write_csv(path: str, rows) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for _category, row in rows:
            writer.writerow(row)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成示例报名数据（合成，可复现）")
    parser.add_argument("--rows", type=int, default=250, help="正常数据行数，默认 250")
    parser.add_argument("--out", default=OUT_DEFAULT, help=f"输出 CSV，默认 {OUT_DEFAULT}")
    parser.add_argument("--notes", default=NOTES_DEFAULT, help=f"输出说明文件，默认 {NOTES_DEFAULT}")
    parser.add_argument("--expect", default=EXPECT_DEFAULT, help="输出期望值 JSON，供测试使用")
    args = parser.parse_args(argv)

    rng = random.Random(SEED)
    notes: dict = {"seed": SEED}
    rows = build_rows(rng, args.rows, notes)
    write_csv(args.out, rows)

    injected = notes["injected"]
    total = len(rows)
    error_rows = sum(injected.get(cat, 0) for cat in ERROR_CATEGORIES)
    # 重复报名里，每组保留第一条，所以真正被剔除的是「涉及行数 - 组数」
    dropped_dups = notes["dup_flagged_rows"] - notes["dup_groups"]
    dropped = error_rows - injected.get("重复报名", 0) + dropped_dups
    expected = {
        "seed": SEED,
        "total_rows": total,
        "injected": injected,
        "identical_dup_groups": notes["identical_dup_groups"],
        "identical_dup_rows": notes["identical_dup_rows"],
        "dup_groups": notes["dup_groups"],
        "dup_flagged_rows": notes["dup_flagged_rows"],
        "expect_error_rows": error_rows,
        "expect_dropped_rows": dropped,
        "expect_clean_rows": total - dropped,
    }

    summary = [
        "# 示例数据说明（由 tools/make_sample_data.py 自动生成，请勿手改）",
        "",
        f"- 文件：`{args.out.replace(os.sep, '/')}`",
        f"- 总行数（不含表头）：**{total}**",
        f"- 随机种子：`{SEED}`（重跑生成脚本可原样复现）",
        "- 数据为**程序合成的假数据**，不含任何真实同学的个人信息。",
        "",
        "## 故意埋进去的问题",
        "",
        "| 类别 | 行数 | 级别 |",
        "| --- | ---: | --- |",
    ]
    for cat, cnt in injected.items():
        level = "错误（会被挡在干净数据之外）" if cat in ERROR_CATEGORIES else "提示（保留，仅在清单里标注）"
        if cat == "正常" or cat.startswith("邮箱域名大写"):
            level = "—"
        summary.append(f"| {cat} | {cnt} | {level} |")
    summary += [
        "",
        "## 期望结论（单元测试据此校验）",
        "",
        f"- 完全重复的行：**{notes['identical_dup_groups']}** 组、共 **{notes['identical_dup_rows']}** 行",
        f"- 重复报名的学号：**{notes['dup_groups']}** 个，涉及 **{notes['dup_flagged_rows']}** 行，"
        f"清洗时每组保留第 1 条、剔除 **{dropped_dups}** 行",
        f"- 问题清单里的行数：**{error_rows}** 行（提示级也进清单的话会更多）",
        f"- 从干净数据里剔除的行数：**{dropped}** 行",
        f"- 清洗后可用数据：**{total - dropped}** 行",
        "",
        "> 精确期望值同时写入了 `tests/expected_sample_counts.json`。",
        "",
    ]

    with open(args.notes, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("\n".join(summary))
    os.makedirs(os.path.dirname(os.path.abspath(args.expect)), exist_ok=True)
    with open(args.expect, "w", encoding="utf-8") as fh:
        json.dump(expected, fh, ensure_ascii=False, indent=2)

    print(f"已生成 {args.out}（{total} 行）")
    print(f"已生成 {args.notes}")
    print(f"已生成 {args.expect}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
