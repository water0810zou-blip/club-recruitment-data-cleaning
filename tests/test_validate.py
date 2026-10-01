"""需求 2（校验与清洗）的单元测试。

运行：
  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import common, validate  # noqa: E402

TINY = os.path.join(ROOT, "tests", "fixtures", "tiny.csv")
SAMPLE = os.path.join(ROOT, "data", "signup_raw.csv")
EXPECT = os.path.join(ROOT, "tests", "expected_sample_counts.json")


def row(line, name="张三", sid="2023000001", email=None,
        c1="项目开发部", c2="", ref=""):
    """造一条数据行（不落盘），便于把每条规则单独拎出来测。"""
    if email is None:
        email = f"{sid}@{validate.EMAIL_DOMAIN}" if sid else ""
    return {"姓名": name, "学号": sid, "邮箱": email,
            "志愿1": c1, "志愿2": c2, "推荐人": ref, common.LINE_KEY: line}


def issues_of(one_row, **kwargs):
    return validate.check_single_row(one_row, one_row[common.LINE_KEY], **kwargs)


def categories(issues):
    return sorted(i.category for i in issues)


class TestIdRule(unittest.TestCase):
    def test_pure_digits(self):
        self.assertTrue(validate.is_pure_digits("2023000001"))

    def test_full_width_digits_rejected(self):
        # Python 的 isdigit() 会认全角数字，但问卷里的全角数字是常见坑，必须判为非法
        self.assertTrue("２０２３".isdigit())
        self.assertFalse(validate.is_pure_digits("２０２３０１０１２３"))

    def test_space_hyphen_and_tail_rejected(self):
        for bad in ["2023 010123", "2023-010123", "2023010123.0", "2023A01234", "学号2023010123"]:
            with self.subTest(bad=bad):
                self.assertFalse(validate.is_pure_digits(bad))
                self.assertIn("id_format", categories(issues_of(row(2, sid=bad))))

    def test_id_length_check_is_opt_in(self):
        short = row(2, sid="20230101")            # 8 位
        self.assertNotIn("id_length", categories(issues_of(short)))          # 默认不校验
        self.assertNotIn("id_length", categories(issues_of(short, id_length=0)))
        warn = issues_of(short, id_length=10)
        self.assertEqual([i.level for i in warn if i.category == "id_length"], [validate.LEVEL_WARN])
        strict = issues_of(short, id_length=10, strict_id_length=True)
        self.assertEqual([i.level for i in strict if i.category == "id_length"], [validate.LEVEL_ERROR])


class TestEmailRule(unittest.TestCase):
    def test_matching_email_passes(self):
        self.assertEqual(issues_of(row(2)), [])

    def test_uppercase_domain_is_accepted(self):
        r = row(2, email="2023000001@SMBU.EDU.CN")
        self.assertEqual(issues_of(r), [])

    def test_prefix_mismatch(self):
        issues = issues_of(row(2, sid="2023010188", email="2023010189@smbu.edu.cn"))
        self.assertIn("email_mismatch", categories(issues))

    def test_wrong_domain(self):
        for bad in ["2023000001@smbu.edu.com", "woshi@qq.com"]:
            with self.subTest(bad=bad):
                self.assertIn("email_mismatch", categories(issues_of(row(2, email=bad))))

    def test_subdomain_counts_as_mismatch(self):
        issues = issues_of(row(2, email="2023000001@stu.smbu.edu.cn"))
        self.assertIn("email_mismatch", categories(issues))

    def test_malformed_email(self):
        for bad in ["2023000001@@smbu.edu.cn", "2023000001@ smbu.edu.cn",
                    "2023000001@smbu", "2023000001"]:
            with self.subTest(bad=bad):
                self.assertIn("email_format", categories(issues_of(row(2, email=bad))))

    def test_invalid_id_does_not_double_report_on_email(self):
        # 学号本身非法时，邮箱不再重复扣分（避免一行刷两条完全同因的错误）
        issues = issues_of(row(2, sid="2023A01234", email="2023A01234@smbu.edu.cn"))
        self.assertEqual(categories(issues), ["id_format"])


class TestRequiredAndWarnings(unittest.TestCase):
    def test_required_blanks(self):
        issues = issues_of(row(2, name="", sid="", email="", c1=""))
        self.assertEqual(categories(issues), ["required_blank"] * 4)
        self.assertTrue(all(i.level == validate.LEVEL_ERROR for i in issues))

    def test_optional_blank_is_not_an_issue(self):
        self.assertEqual(issues_of(row(2, c2="", ref="")), [])

    def test_same_two_choices_is_warning_only(self):
        issues = issues_of(row(2, c1="项目开发部", c2="项目开发部"))
        self.assertEqual(categories(issues), ["choice_same"])
        self.assertEqual(issues[0].level, validate.LEVEL_WARN)

    def test_unknown_department_is_warning_only(self):
        issues = issues_of(row(2, c1="电竞部"))
        self.assertEqual(categories(issues), ["choice_unknown"])
        self.assertEqual(issues[0].level, validate.LEVEL_WARN)

    def test_name_with_digit_is_warning_only(self):
        issues = issues_of(row(2, name="李四2"))
        self.assertEqual(categories(issues), ["name_suspect"])
        self.assertEqual(issues[0].level, validate.LEVEL_WARN)


class TestDuplicateSignups(unittest.TestCase):
    def test_same_id_twice_is_flagged_on_both_rows(self):
        rows = [row(2, sid="2023000001"), row(5, name="李四", sid="2023000001")]
        issues, groups = validate.validate(rows)
        self.assertEqual(groups, {"2023000001": [2, 5]})
        self.assertIn("duplicate", categories(issues[2]))
        self.assertIn("duplicate", categories(issues[5]))
        self.assertIn("第 2 次出现", issues[5][0].detail)

    def test_blank_ids_are_not_duplicates(self):
        rows = [row(2, sid=""), row(3, name="李四", sid=""), row(4, sid="2023000009")]
        _issues, groups = validate.validate(rows)
        self.assertEqual(groups, {})

    def test_different_ids_are_not_duplicates(self):
        rows = [row(2, sid="2023000001"), row(3, name="李四", sid="2023000002")]
        _issues, groups = validate.validate(rows)
        self.assertEqual(groups, {})


class TestCleanSplit(unittest.TestCase):
    def test_first_submission_kept_others_dropped(self):
        rows = [row(2, sid="2023000001", c1="项目开发部"),
                row(5, name="李四", sid="2023000001", c1="品牌传播部")]
        issues, groups = validate.validate(rows)
        clean, dropped = validate.split_clean(rows, issues, groups)
        self.assertEqual([r[common.LINE_KEY] for r in clean], [2])
        self.assertEqual([r[common.LINE_KEY] for r, _ in dropped], [5])

    def test_error_rows_are_dropped_warning_rows_are_kept(self):
        rows = [row(2, sid="2023A01234"),            # 错误：学号非纯数字
                row(3, c1="项目开发部", c2="项目开发部"),     # 提示：不算错
                row(4, email="x@qq.com")]           # 错误：邮箱不匹配
        issues, groups = validate.validate(rows)
        clean, dropped = validate.split_clean(rows, issues, groups)
        self.assertEqual([r[common.LINE_KEY] for r in clean], [3])
        self.assertEqual(sorted(r[common.LINE_KEY] for r, _ in dropped), [2, 4])

    def test_drop_all_duplicates_option(self):
        rows = [row(2, sid="2023000001"), row(5, sid="2023000001")]
        issues, groups = validate.validate(rows)
        clean, dropped = validate.split_clean(rows, issues, groups, drop_all_duplicates=True)
        self.assertEqual(clean, [])
        self.assertEqual(len(dropped), 2)


class TestProblemExports(unittest.TestCase):
    def test_problem_list_only_contains_problem_rows(self):
        rows = [row(2), row(3, sid="2023A01234")]
        issues, _groups = validate.validate(rows)
        exported = validate.build_problem_rows(rows, issues, list(common.COLUMNS))
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["行号"], 3)
        self.assertIn("不是纯数字", exported[0]["问题说明"])

    def test_detail_has_one_row_per_issue(self):
        rows = [row(2, name="", sid="")]          # 姓名/学号/邮箱 三项为空 → 3 条
        issues, _groups = validate.validate(rows)
        detail = validate.build_problem_detail(rows, issues, list(common.COLUMNS))
        self.assertEqual(len(detail), 3)


class TestReadOnlyGuarantee(unittest.TestCase):
    def test_input_file_is_never_modified(self):
        tmp = tempfile.mkdtemp(prefix="smbu-test-")
        try:
            target = os.path.join(tmp, "报名.csv")
            shutil.copy(TINY, target)
            before = validate.file_digest(target)
            code = validate.main(["--input", target, "--output-dir", os.path.join(tmp, "out")])
            self.assertEqual(code, 0)
            self.assertEqual(before, validate.file_digest(target))
            self.assertTrue(os.path.exists(os.path.join(tmp, "out", "问题清单.csv")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fail_on_error_exit_code(self):
        tmp = tempfile.mkdtemp(prefix="smbu-test-")
        try:
            target = os.path.join(tmp, "报名.csv")
            shutil.copy(TINY, target)
            self.assertEqual(validate.main(["--input", target, "-o", os.path.join(tmp, "o")]), 0)
            self.assertEqual(validate.main(["--input", target, "-o", os.path.join(tmp, "o"),
                                            "--fail-on-error"]), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestSampleDataExpectations(unittest.TestCase):
    """示例数据里的坑是脚本埋的，期望值也是脚本独立算的 —— 两边必须对上。"""

    @unittest.skipUnless(os.path.exists(SAMPLE) and os.path.exists(EXPECT), "缺少示例数据")
    def setUp(self):
        with open(EXPECT, encoding="utf-8") as fh:
            self.expect = json.load(fh)
        _raw, self.columns, self.rows, _meta = common.read_csv_rows(SAMPLE)
        self.issues, self.groups = validate.validate(self.rows)

    def test_duplicate_groups(self):
        self.assertEqual(len(self.groups), self.expect["dup_groups"])
        self.assertEqual(sum(len(v) for v in self.groups.values()), self.expect["dup_flagged_rows"])

    def test_error_and_clean_counts(self):
        problem_lines = [ln for ln, iss in self.issues.items() if iss]
        error_lines = [ln for ln, iss in self.issues.items()
                       if any(i.level == validate.LEVEL_ERROR for i in iss)]
        clean, dropped = validate.split_clean(self.rows, self.issues, self.groups)
        self.assertEqual(len(error_lines), self.expect["expect_error_rows"])
        self.assertEqual(len(dropped), self.expect["expect_dropped_rows"])
        self.assertEqual(len(clean), self.expect["expect_clean_rows"])
        self.assertGreaterEqual(len(problem_lines), self.expect["expect_error_rows"])

    def test_every_injected_problem_is_caught(self):
        """埋进去的每一类坑都要被抓到，防止规则悄悄失灵。"""
        seen = {i.category for iss in self.issues.values() for i in iss}
        for expected_category in ["required_blank", "id_format", "email_mismatch",
                                 "email_format", "duplicate", "choice_same",
                                 "choice_unknown", "name_suspect"]:
            with self.subTest(category=expected_category):
                self.assertIn(expected_category, seen)


if __name__ == "__main__":
    unittest.main()
