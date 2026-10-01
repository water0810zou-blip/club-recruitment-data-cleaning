"""common.py —— 公共地基：字段定义、CSV 读写、文本规范化。

本模块只放三个需求都要用的基础能力，不含任何业务规则
（「什么算错」的规则全部放在 validate.py，见需求 2）。

设计原则：
1. 只用 Python 标准库，不引入任何第三方依赖 —— 招新现场随便一台电脑都能跑。
2. 读入永远只读：本模块不会以写模式打开输入文件。
3. 输出统一用 utf-8-sig 编码，这样双击用 Excel / WPS 打开不会乱码。
"""

from __future__ import annotations

import csv
import os
import re
import sys
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------
# 一、字段定义
# --------------------------------------------------------------------------

# 问卷导出 CSV 的目标字段（顺序即输出顺序）
COLUMNS: List[str] = ["姓名", "学号", "邮箱", "志愿1", "志愿2", "推荐人"]

# 必填字段：为空视为「有问题」，需要进问题清单
REQUIRED_COLUMNS: List[str] = ["姓名", "学号", "邮箱", "志愿1"]

# 选填字段：为空只是信息缺失，不算错误
OPTIONAL_COLUMNS: List[str] = ["志愿2", "推荐人"]

# 表头别名：问卷平台导出的表头常常带上题号或口语化写法，这里做一层归一
HEADER_ALIASES: Dict[str, str] = {
    "姓名": "姓名", "名字": "姓名", "真实姓名": "姓名", "你的姓名": "姓名", "name": "姓名",
    "学号": "学号", "学籍号": "学号", "学生学号": "学号", "id": "学号", "studentid": "学号",
    "邮箱": "邮箱", "电子邮箱": "邮箱", "邮件": "邮箱", "email": "邮箱", "e-mail": "邮箱", "mail": "邮箱",
    "志愿1": "志愿1", "志愿一": "志愿1", "第一志愿": "志愿1", "首选志愿": "志愿1",
    "志愿2": "志愿2", "志愿二": "志愿2", "第二志愿": "志愿2", "次选志愿": "志愿2",
    "推荐人": "推荐人", "推荐": "推荐人", "介绍人": "推荐人", "谁推荐的": "推荐人",
}

# 输出编码：带 BOM 的 utf-8，Excel 打开中文不乱码
OUTPUT_ENCODING = "utf-8-sig"

# 读入时依次尝试的编码
INPUT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

# 每行数据上挂的物理行号字段（表头 = 第 1 行，第一条数据 = 第 2 行）
LINE_KEY = "__line__"

# --------------------------------------------------------------------------
# 一之二、部门与中心（协会现行组织结构）
# --------------------------------------------------------------------------
# 三个中心各自下设若干部门。招新「志愿」的合法取值是**部门**；
# 中心是上层归类，只用于在汇总时把同一中心的部门并成一条（见需求 3「按中心汇总」），
# 不作为志愿选项 —— 填了中心名属于填错部门，会被「志愿不在部门清单内」标为提示。
DEPARTMENT_CENTERS: Dict[str, str] = {
    # 技术研发中心（TRDC）：聚焦技术创新与项目落地
    "创新创业部": "技术研发中心",
    "项目开发部": "技术研发中心",
    "课程研发部": "技术研发中心",
    # 运营管理中心（OMC）：负责协会内部运转与品牌建设
    "综合行政部": "运营管理中心",
    "品牌传播部": "运营管理中心",
    # 对外合作中心（ECC）：拓展校内外各类合作资源
    "战略关系部": "对外合作中心",
    "赛事运营部": "对外合作中心",
}

# 中心清单（对应部门清单的顺序，用于「按中心汇总」时保证顺序稳定）
CENTERS: List[str] = [
    "技术研发中心", "运营管理中心", "对外合作中心",
]

# 志愿可选部门。用于「志愿填了清单外的部门」这条提示级检查，可用 --choices 覆盖。
DEFAULT_DEPARTMENTS: Tuple[str, ...] = tuple(DEPARTMENT_CENTERS)


class DataFileError(Exception):
    """输入文件本身不可用（不存在、表头缺列等）时抛出，用于给出人话报错。"""


# --------------------------------------------------------------------------
# 二、文本规范化
# --------------------------------------------------------------------------

# 各类不可见字符：BOM、零宽空格、零宽连接符、不间断空格
_INVISIBLE = {
    "\ufeff", "\u200b", "\u200c", "\u200d", "\u2060", "\xa0", "\u3000",
    "\u2028", "\u2029", "\t", "\r", "\n",
}


def normalize(value) -> str:
    """把一个单元格的值规范化为干净的字符串。

    做三件事：None 变空串、去掉首尾与内部的不可见字符、去掉首尾空白。
    不改变任何可见内容和大小写 —— 大小写属于业务规则，交回 validate.py 判断。
    """
    if value is None:
        return ""
    text = str(value)
    for ch in _INVISIBLE:
        if ch in text:
            text = text.replace(ch, " " if ch in ("\t", "\r", "\n", "\u3000") else "")
    # 连续空格压成一个，避免「张 三」和「张三」看起来不同
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def display_width(text: str) -> int:
    """估算字符串在等宽终端里的显示宽度（中文算 2 格），用于对齐打印。"""
    import unicodedata

    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text: str, width: int, align: str = "left") -> str:
    """按显示宽度补空格，让中文表格在终端里能对齐。"""
    text = str(text)
    gap = max(0, width - display_width(text))
    return (" " * gap + text) if align == "right" else (text + " " * gap)


def truncate(text: str, width: int) -> str:
    """按显示宽度截断，超出部分用 … 结尾（只用于打印，不改数据）。"""
    text = str(text)
    if display_width(text) <= width:
        return text
    out, used = "", 0
    for ch in text:
        w = 2 if __import__("unicodedata").east_asian_width(ch) in ("W", "F") else 1
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def enable_utf8_output() -> None:
    """让脚本在 Windows 终端（默认 GBK）里也能正常打印中文。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def ensure_dir(path: str) -> str:
    """确保目录存在（输入是文件路径时取其父目录）。"""
    if not path:
        return path
    if os.path.splitext(os.path.basename(path))[1]:
        path = os.path.dirname(path)
    if path:
        os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# 三、CSV 读入
# --------------------------------------------------------------------------

def _canonical_header(raw: str) -> str:
    """把原始表头归一成标准列名；认不出来的列原样保留（并在概览里提示）。"""
    head = normalize(raw)
    head = re.sub(r"^\s*\d+\s*[.、)．]\s*", "", head)   # 去掉「1. 」「3、」这类题号
    compact = head.replace(" ", "")
    key = compact.lower()
    if key in HEADER_ALIASES:
        return HEADER_ALIASES[key]
    if compact in COLUMNS:
        return compact
    # 模糊匹配：包含「学号」「邮箱」等关键词即可
    for col in COLUMNS:
        if col in compact:
            return col
    if re.search(r"(第一|首个|一)\s*志愿", compact):
        return "志愿1"
    if re.search(r"(第二|次选|二)\s*志愿", compact):
        return "志愿2"
    return head or "(空列名)"


def _sniff_encoding(path: str) -> str:
    """依次尝试常见编码，返回第一个能解码整个文件的编码。"""
    last_error: Exception | None = None
    for enc in INPUT_ENCODINGS:
        try:
            with open(path, "r", encoding=enc, newline="") as fh:
                fh.read()
            return enc
        except (UnicodeDecodeError, LookupError) as exc:  # pragma: no cover
            last_error = exc
    raise DataFileError(
        f"无法识别 {path} 的编码（已尝试 {', '.join(INPUT_ENCODINGS)}），"
        f"请另存为 UTF-8 或 GBK。最后一次错误：{last_error}"
    )


def read_csv_rows(path: str) -> Tuple[List[str], List[str], List[Dict[str, str]], Dict[str, int]]:
    """读入报名 CSV（只读，绝不修改原文件）。

    返回四元组：
        raw_headers  原始表头
        columns      归一后的列名
        rows         数据行（dict，另带 LINE_KEY 记录文件物理行号）
        meta         读入过程的元信息（encoding / blank_lines / total_lines）
    """
    if not os.path.exists(path):
        raise DataFileError(f"找不到输入文件：{path}")
    if os.path.isdir(path):
        raise DataFileError(f"输入路径是文件夹，需要具体到某个 .csv 文件：{path}")

    encoding = _sniff_encoding(path)
    with open(path, "r", encoding=encoding, newline="") as fh:
        reader = csv.reader(fh)
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise DataFileError(f"文件是空的：{path}")

        columns = [_canonical_header(h) for h in raw_headers]
        # 同名列（例如问卷里两个字段都被识别成「姓名」）加后缀避免互相覆盖
        seen: Dict[str, int] = {}
        for idx, col in enumerate(columns):
            if col in seen:
                seen[col] += 1
                columns[idx] = f"{col}#{seen[col]}"
            else:
                seen[col] = 0

        rows: List[Dict[str, str]] = []
        blank_lines = 0
        for line_no, raw_row in enumerate(reader, start=2):
            if not any(normalize(cell) for cell in raw_row):
                blank_lines += 1
                continue
            row = {col: normalize(raw_row[i]) if i < len(raw_row) else ""
                   for i, col in enumerate(columns)}
            row[LINE_KEY] = line_no
            rows.append(row)

    meta = {"encoding": encoding, "blank_lines": blank_lines,
            "total_lines": len(rows) + blank_lines + 1}
    return raw_headers, columns, rows, meta


def check_required_columns(columns: List[str]) -> Tuple[List[str], List[str]]:
    """检查必填列是否齐全，返回 (缺失的必填列, 多出来的未知列)。"""
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    unknown = [c for c in columns if c not in COLUMNS]
    return missing, unknown


# --------------------------------------------------------------------------
# 四、CSV 写出
# --------------------------------------------------------------------------

def write_csv(path: str, fieldnames: List[str], rows: List[Dict[str, object]]) -> str:
    """写出 CSV（utf-8-sig，Excel 友好）。返回写出的绝对路径。"""
    ensure_dir(path)
    with open(path, "w", encoding=OUTPUT_ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return os.path.abspath(path)


def write_text(path: str, text: str) -> str:
    """写出文本报告（utf-8-sig）。"""
    ensure_dir(path)
    with open(path, "w", encoding=OUTPUT_ENCODING, newline="") as fh:
        fh.write(text)
    return os.path.abspath(path)


def source_fields(columns: List[str]) -> List[str]:
    """数据行的原始业务字段（不含 LINE_KEY 这类内部字段），按标准列顺序排列。"""
    ordered = [c for c in COLUMNS if c in columns]
    extra = [c for c in columns if c not in COLUMNS]
    return ordered + extra
