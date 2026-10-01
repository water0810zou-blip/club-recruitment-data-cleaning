"""需求 1（读入与概览）的单元测试。

运行：
  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import common, overview  # noqa: E402

TINY = os.path.join(ROOT, "tests", "fixtures", "tiny.csv")
SAMPLE = os.path.join(ROOT, "data", "signup_raw.csv")
EXPECT = os.path.join(ROOT, "tests", "expected_sample_counts.json")


class TestTinyFixture(unittest.TestCase):
    """用一份 5 行的小数据把口径钉死，避免依赖大文件。"""

    @classmethod
    def setUpClass(cls):
        cls.result = overview.analyze(TINY)

    def test_row_count_ignores_header(self):
        self.assertEqual(self.result["row_count"], 5)

    def test_columns_are_normalized(self):
        self.assertEqual(self.result["columns"], common.COLUMNS)

    def test_blank_count_per_column(self):
        blanks = dict(self.result["blanks"])
        self.assertEqual(blanks["姓名"], 1)
        self.assertEqual(blanks["学号"], 0)
        self.assertEqual(blanks["邮箱"], 0)
        self.assertEqual(blanks["志愿1"], 1)
        self.assertEqual(blanks["志愿2"], 3)
        self.assertEqual(blanks["推荐人"], 2)

    def test_required_blank_rows(self):
        # 第 4 行缺姓名、第 5 行缺志愿1
        self.assertEqual(self.result["blank_required_rows"], 2)

    def test_identical_duplicate_rows(self):
        groups = self.result["dup_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0], [2, 4])       # 表头是第 1 行，数据从第 2 行开始


class TestAgainstSampleData(unittest.TestCase):
    """对示例数据做一致性校验（期望值由生成脚本独立算出）。"""

    @unittest.skipUnless(os.path.exists(SAMPLE) and os.path.exists(EXPECT), "缺少示例数据")
    def test_sample_row_count(self):
        with open(EXPECT, encoding="utf-8") as fh:
            expect = json.load(fh)
        result = overview.analyze(SAMPLE)
        self.assertEqual(result["row_count"], expect["total_rows"])
        self.assertEqual(len(result["dup_groups"]), expect["identical_dup_groups"])
        self.assertEqual(result["dup_rows"], expect["identical_dup_rows"])

    def test_headless_run_returns_zero(self):
        self.assertEqual(overview.main(["--input", TINY]), 0)


class TestBadInput(unittest.TestCase):
    def test_missing_file_gives_friendly_error(self):
        with self.assertRaises(common.DataFileError):
            overview.analyze(os.path.join(ROOT, "tests", "fixtures", "不存在.csv"))


if __name__ == "__main__":
    unittest.main()
