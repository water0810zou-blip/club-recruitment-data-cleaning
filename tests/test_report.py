"""需求 3（统计与导出）的单元测试。

运行：
  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import common, report, validate  # noqa: E402

SAMPLE = os.path.join(ROOT, "data", "signup_raw.csv")
EXPECT = os.path.join(ROOT, "tests", "expected_sample_counts.json")
TINY = os.path.join(ROOT, "tests", "fixtures", "tiny.csv")


def row(line, name="张三", sid="2023000001", email=None, c1="项目开发部", c2="", ref=""):
    if email is None:
        email = f"{sid}@{validate.EMAIL_DOMAIN}" if sid else ""
    return {"姓名": name, "学号": sid, "邮箱": email,
            "志愿1": c1, "志愿2": c2, "推荐人": ref, common.LINE_KEY: line}


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class TestGrouping(unittest.TestCase):
    def test_count_and_order(self):
        rows = [row(2, c1="项目开发部"), row(3, name="李四", sid="2023000002", c1="品牌传播部"),
                row(4, name="王五", sid="2023000003", c1="项目开发部"),
                row(5, name="赵六", sid="2023000004", c1="项目开发部")]
        grouped = report.count_by_first_choice(rows)
        self.assertEqual(grouped[0][:2], ("项目开发部", 3))
        self.assertEqual(grouped[1][:2], ("品牌传播部", 1))
        self.assertAlmostEqual(grouped[0][2], 0.75)

    def test_blank_first_choice_is_kept_as_unknown(self):
        rows = [row(2, c1=""), row(3, name="李四", sid="2023000002", c1="项目开发部")]
        grouped = dict((c, n) for c, n, _r in report.count_by_first_choice(rows))
        self.assertEqual(grouped["(未填写)"], 1)

    def test_count_by_center_merges_departments_of_one_center(self):
        rows = [row(2, c1="项目开发部"), row(3, c1="创新创业部"),   # 都在技术研发中心
                row(4, c1="品牌传播部"),                          # 运营管理中心
                row(5, c1="赛事运营部")]                          # 对外合作中心
        centers = dict((c, n) for c, n, _r in report.count_by_center(rows))
        self.assertEqual(centers["技术研发中心"], 2)
        self.assertEqual(centers["运营管理中心"], 1)
        self.assertEqual(centers["对外合作中心"], 1)
        self.assertAlmostEqual(sum(centers.values()), len(rows))

    def test_count_by_center_keeps_unmapped_value_apart(self):
        # 误填成中心名、或乱填的脏数据：单独归一类，不能静默丢掉
        rows = [row(2, c1="技术研发中心"), row(3, c1="电竞部")]
        centers = dict((c, n) for c, n, _r in report.count_by_center(rows))
        self.assertEqual(centers["(志愿不在中心清单内)"], 2)

    def test_completeness_buckets_are_mutually_exclusive(self):
        rows = [row(2, c2="品牌传播部"),                    # 两个都填
                row(3, name="李四", sid="2023000002"),  # 只填第一志愿
                row(4, name="王五", sid="2023000003", c1="", c2="综合行政部"),   # 只填第二志愿
                row(5, name="赵六", sid="2023000004", c1="", c2="")]         # 都没填
        stats = dict((label, cnt) for label, cnt, _r in report.count_choice_completeness(rows))
        self.assertEqual(stats["两个志愿都填了"], 1)
        self.assertEqual(stats["只填了第一志愿"], 1)
        self.assertEqual(stats["只填了第二志愿"], 1)
        self.assertEqual(stats["两个志愿都没填"], 1)
        self.assertEqual(sum(stats.values()), len(rows))


class TestCleanExport(unittest.TestCase):
    def test_clean_export_has_line_number_first(self):
        rows = [row(7, c1="项目开发部")]
        exported = report.build_clean_rows(rows, list(common.COLUMNS))
        self.assertEqual(list(exported[0].keys())[0], report.LINE_COLUMN)
        self.assertEqual(exported[0][report.LINE_COLUMN], 7)
        self.assertEqual(exported[0]["姓名"], "张三")


class TestEndToEnd(unittest.TestCase):
    """用示例数据真跑一遍，检查产物的自洽性。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="smbu-report-")
        cls.result = report.run(SAMPLE, cls.tmp, verbose=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_all_expected_files_exist(self):
        for name in ["汇总表_按第一志愿.csv", "汇总表_双志愿填写情况.csv", "汇总表.md",
                     "清洗后数据.csv", "被剔除的行.csv", "统计报告.txt"]:
            with self.subTest(name=name):
                self.assertTrue(os.path.exists(os.path.join(self.tmp, name)), name)

    def test_summary_total_equals_clean_row_count(self):
        summary = read_csv(os.path.join(self.tmp, "汇总表_按第一志愿.csv"))
        self.assertEqual(summary[-1]["第一志愿"], "合计")
        self.assertEqual(int(summary[-1]["人数"]), len(self.result["clean_rows"]))
        detail_total = sum(int(r["人数"]) for r in summary[:-1])
        self.assertEqual(detail_total, int(summary[-1]["人数"]))

    def test_everyone_counted_exactly_once(self):
        grouped = sum(cnt for _c, cnt, _r in self.result["by_first"])
        self.assertEqual(grouped, len(self.result["clean_rows"]))

    def test_clean_data_contains_no_error_rows(self):
        clean = read_csv(os.path.join(self.tmp, "清洗后数据.csv"))
        self.assertEqual(len(clean), len(self.result["clean_rows"]))
        error_lines = {int(r.get(common.LINE_KEY)) for r in self.result["rows"]
                       if any(i.level == validate.LEVEL_ERROR
                              for i in self.result["issues_by_line"].get(int(r[common.LINE_KEY]), []))}
        kept_lines = {int(r[report.LINE_COLUMN]) for r in clean}
        # 只有「重复报名的第 1 次提交」允许既是错误行又出现在干净数据里
        leaked = kept_lines & error_lines
        for line in leaked:
            issues = self.result["issues_by_line"][line]
            self.assertTrue(all(i.category == "duplicate" for i in issues))

    def test_dropped_rows_are_accounted_for(self):
        dropped = read_csv(os.path.join(self.tmp, "被剔除的行.csv"))
        self.assertEqual(len(dropped), len(self.result["dropped"]))
        self.assertEqual(len(dropped) + len(self.result["clean_rows"]), len(self.result["rows"]))

    def test_rerun_is_idempotent(self):
        """同样的输入跑两次，产物应当逐字节一致（便于放进 CI 或反复复核）。"""
        second = tempfile.mkdtemp(prefix="smbu-report2-")
        try:
            report.run(SAMPLE, second, verbose=False)
            for name in ["汇总表_按第一志愿.csv", "清洗后数据.csv", "汇总表.md"]:
                with self.subTest(name=name):
                    with open(os.path.join(self.tmp, name), "rb") as f1, \
                         open(os.path.join(second, name), "rb") as f2:
                        self.assertEqual(f1.read(), f2.read())
        finally:
            shutil.rmtree(second, ignore_errors=True)

    @unittest.skipUnless(os.path.exists(EXPECT), "缺少示例数据期望值")
    def test_matches_sample_expectations(self):
        with open(EXPECT, encoding="utf-8") as fh:
            expect = json.load(fh)
        self.assertEqual(len(self.result["clean_rows"]), expect["expect_clean_rows"])
        self.assertEqual(len(self.result["dropped"]), expect["expect_dropped_rows"])

    def test_keep_problems_switch_changes_scope(self):
        tmp = tempfile.mkdtemp(prefix="smbu-report3-")
        try:
            stats = report.run(SAMPLE, tmp, keep_problems=True, verbose=False)
            total = sum(cnt for _c, cnt, _r in stats["by_first"])
            self.assertEqual(total, len(stats["rows"]))
            self.assertGreater(total, len(stats["clean_rows"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCliOnTinyFile(unittest.TestCase):
    def test_main_returns_zero(self):
        tmp = tempfile.mkdtemp(prefix="smbu-report4-")
        try:
            self.assertEqual(report.main(["-i", TINY, "-o", tmp]), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_file_gives_friendly_error(self):
        tmp = tempfile.mkdtemp(prefix="smbu-report5-")
        try:
            self.assertEqual(report.main(["-i", os.path.join(tmp, "没有.csv"), "-o", tmp]), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
