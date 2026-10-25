"""菜品名归一化。

对应 SPEC-ai-food-recognition.md §3.2。

## 这个模块唯一要防的事：过度剥离

把修饰词剥掉是好的，但剥过头会把菜品名变成食材名甚至调料名：

| 输入 | 若剥离 | 结果 | 判断 |
|---|---|---|---|
| 蛋炒饭 | 剥「炒饭」 | **蛋** | 荒谬 |
| 葱油拌面 | 剥「拌面」 | **葱油** | 变成调料名 |
| 卤肉饭 | 剥「饭」 | **卤肉** | 变成食材名 |
| 兰州牛肉面 | 剥「面」 | **兰州牛肉** | 不可辨识 |

所以规则只有一条铁律：

> **绝不剥离「饭 / 面 / 粉 / 汤」这类可能是菜名本体的单字。**
> 剥离表只收**多字、且明确表示盛放形式 / 规格 / 来源**的词。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: 前缀剥离：表示来源 / 地域 / 修饰，去掉后菜品本体不变
PREFIX_STRIP: tuple[str, ...] = (
    "自制", "家常", "妈妈", "私房", "招牌", "秘制", "正宗", "特色",
    "手工", "传统", "经典",
    "台湾", "四川", "广东", "湖南", "北京", "上海",
    "日式", "韩式", "泰式", "意式",
)

#: 后缀剥离：表示盛放形式 / 规格 / 份量。
#: **全部为多字词**，不含「饭 / 面 / 粉 / 汤」单字。
#: 按长度降序排列，保证最长匹配优先。
SUFFIX_STRIP: tuple[str, ...] = tuple(
    sorted(
        (
            "盖浇饭", "盖码饭", "盖饭", "盖浇",
            "套餐", "外卖", "便当", "定食",
            "拼盘", "双拼", "三拼",
            "一份", "中份", "大份", "小份", "例份",
            "加饭", "配饭",
        ),
        key=len,
        reverse=True,
    )
)

#: 括号及其内容，如「（微辣）」「(小份)」
_BRACKET_RE = re.compile(r"[\(（【\[][^)）】\]]*[\)）】\]]")

#: 只保留汉字、英文字母、数字；其余（空白、标点、符号、emoji）全部去掉
_KEEP_RE = re.compile(r"[^一-鿿A-Za-z0-9]")


def clean_dish_name(raw: str) -> str:
    """基础清洗：去括号内容、去空白与标点。

    >>> clean_dish_name("宫保鸡丁（微辣）")
    '宫保鸡丁'
    >>> clean_dish_name("宫保鸡丁 盖饭")
    '宫保鸡丁盖饭'
    """
    if not raw:
        return ""
    without_bracket = _BRACKET_RE.sub("", raw)
    return _KEEP_RE.sub("", without_bracket)


def _strip_prefix(name: str) -> str:
    for prefix in PREFIX_STRIP:
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix) :]
    return name


def _strip_suffix(name: str) -> str:
    for suffix in SUFFIX_STRIP:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def _strip_all(name: str) -> str:
    """反复剥离直到没有任何规则命中。"""
    current = name
    while True:
        nxt = _strip_suffix(_strip_prefix(current))
        if nxt == current or not nxt:
            return current if current else name
        current = nxt


def normalize_dish_name(raw: str) -> str:
    """归一化：清洗 + 剥离修饰词。返回用于存储与匹配的 `normalized_name`。

    >>> normalize_dish_name("宫保鸡丁盖饭")
    '宫保鸡丁'
    >>> normalize_dish_name("自制宫保鸡丁")
    '宫保鸡丁'
    >>> normalize_dish_name("蛋炒饭")
    '蛋炒饭'
    """
    cleaned = clean_dish_name(raw)
    if not cleaned:
        return ""
    return _strip_all(cleaned)


def name_variants(raw: str) -> list[str]:
    """按优先级生成候选名，用于「匹配优先」的试探。

    顺序：
    1. 清洗后的原名
    2. 单独应用每条前缀规则的结果
    3. 单独应用每条后缀规则的结果
    4. 全部规则反复剥离的结果（最激进，但也最可能命中）
    """
    cleaned = clean_dish_name(raw)
    if not cleaned:
        return []

    out: list[str] = []

    def add(value: str) -> None:
        if value and value not in out:
            out.append(value)

    add(cleaned)

    for prefix in PREFIX_STRIP:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
            add(cleaned[len(prefix) :])

    for suffix in SUFFIX_STRIP:
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            add(cleaned[: -len(suffix)])

    add(_strip_all(cleaned))
    return out


def resolve_recipe_name(raw: str, existing: Iterable[str]) -> str | None:
    """在已有菜品名里试探匹配，返回命中的那个；没命中返回 None。

    这是「同名直接复用」的入口——命中就不要再调 AI，省一次配额。

    >>> resolve_recipe_name("宫保鸡丁盖饭", ["宫保鸡丁"])
    '宫保鸡丁'
    >>> resolve_recipe_name("麻辣烫", ["宫保鸡丁"]) is None
    True
    """
    existing_set = set(existing)
    for candidate in name_variants(raw):
        if candidate in existing_set:
            return candidate
    return None
