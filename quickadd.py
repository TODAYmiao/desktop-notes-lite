"""自然语言快速添加解析器。

目标只有一个：把「记录一条待办」的耗时压到 3 秒以内 —— 手不离键盘，
在一行里写「评审材料 明天 15:00 !!」就能同时定好日期、提醒与优先级。

支持的语法（可自由组合，顺序无关）：

    日期   今天 / 明天 / 后天 / 大后天 / 下周一 / 下周天
           10月30日 / 6月1号 / 2026-12-24 / +3d / +2w / +1m
    时间   @15:00 / @9点 / @9点半 / @21点30分
    优先级 ! / !!（对应 高 / 紧急）
    重复   ~每天 / ~工作日 / ~每周三 / ~每月1日

未被识别的部分就是任务正文。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

WEEKDAY_NAMES = "一二三四五六日"
WEEKDAY_FULL = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
PRIORITY_LABELS = {0: "普通", 1: "高", 2: "紧急"}
RULE_LABELS = {
    "daily": "每天",
    "weekdays": "工作日",
    "weekly": "每周",
    "monthly": "每月",
}

_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_MONTH_DAY_RE = re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]")
_OFFSET_RE = re.compile(r"\+(\d{1,3})\s*([dwm])(?![a-z])", re.IGNORECASE)
_NEXT_WEEK_RE = re.compile(r"下(?:周|星期|礼拜)([一二三四五六日天])")
_DAY_WORD_RE = re.compile(r"(?<![明后])今天|(?<![明])明天|(?<![大])后天|大后天")
_TIME_COLON_RE = re.compile(r"@(\d{1,2}):(\d{2})")
_TIME_CN_RE = re.compile(r"@?(\d{1,2})点(?:(\d{1,2})分|半)?")
_PRIORITY_RE = re.compile(r"(?<!\S)(!{1,3})(?!\S)")
_DAILY_RE = re.compile(r"~\s*(每天|每日)")
_WEEKDAYS_RE = re.compile(r"~\s*工作日")
_WEEKLY_RE = re.compile(r"~\s*(?:每周|每星期|每礼拜)([一二三四五六日天])")
_MONTHLY_RE = re.compile(r"~\s*每月(\d{1,2})[日号]")

MAX_TEXT = 200


@dataclass
class ParsedQuickAdd:
    text: str = ""
    target_date: date | None = None
    remind_at: str | None = None
    priority: int = 0
    series: dict | None = None
    matched: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def summary(self) -> str:
        """给输入框下方预览用的中文摘要。"""
        parts: list[str] = []
        if self.target_date is not None:
            parts.append(format_day(self.target_date))
        if self.remind_at:
            parts.append(self.remind_at)
        if self.priority:
            parts.append(PRIORITY_LABELS.get(self.priority, ""))
        if self.series:
            parts.append(describe_series(self.series))
        return " · ".join(p for p in parts if p)


def format_day(value: date, today: date | None = None) -> str:
    today = today or date.today()
    delta = (value - today).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    if delta == 2:
        return "后天"
    if delta == -1:
        return "昨天"
    if 0 < delta <= 6:
        return WEEKDAY_FULL[value.weekday()]
    if value.year == today.year:
        return f"{value.month}月{value.day}日"
    return f"{value.year}年{value.month}月{value.day}日"


def describe_series(series: dict) -> str:
    rule = series.get("rule")
    if rule == "weekly":
        days = series.get("weekdays") or []
        if len(days) == 7:
            return "每天"
        if days:
            return "每周" + "、".join(WEEKDAY_NAMES[d % 7] for d in days)
        return "每周"
    if rule == "monthly":
        return f"每月{series.get('dayOfMonth', 1)}日"
    return RULE_LABELS.get(rule, "重复")


def _next_week_day(today: date, name: str) -> date:
    index = WEEKDAY_NAMES.index(name) if name in WEEKDAY_NAMES else 0
    if name == "天":
        index = 6
    # 下一个自然周的周一
    monday = today + timedelta(days=(7 - today.weekday()))
    return monday + timedelta(days=index)


def _resolve_month_day(today: date, month: int, day: int) -> date:
    year = today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return today
    if candidate < today - timedelta(days=1):
        try:
            candidate = date(year + 1, month, day)
        except ValueError:
            return candidate
    return candidate


def parse_quick_add(raw: str, today: date | None = None) -> ParsedQuickAdd:
    """把一行文本解析成结构化草稿。解析失败时退回「整行当正文」。"""
    today = today or date.today()
    text = (raw or "").strip()
    result = ParsedQuickAdd()
    if not text:
        return result

    spans: list[tuple[int, int]] = []

    def cut(match: re.Match) -> None:
        spans.append(match.span())

    # ---- 重复规则（先扫，因为「每天」里含有日期词的味道）----
    match = _MONTHLY_RE.search(text)
    if match:
        day = max(1, min(28, int(match.group(1))))
        result.series = {
            "rule": "monthly",
            "weekdays": [],
            "dayOfMonth": day,
        }
        result.matched.append("monthly")
        cut(match)
    match = _WEEKLY_RE.search(text)
    if match:
        name = match.group(1)
        index = 6 if name == "天" else WEEKDAY_NAMES.index(name)
        result.series = {"rule": "weekly", "weekdays": [index], "dayOfMonth": 0}
        result.matched.append("weekly")
        cut(match)
    match = _WEEKDAYS_RE.search(text)
    if match:
        result.series = {
            "rule": "weekdays",
            "weekdays": [0, 1, 2, 3, 4],
            "dayOfMonth": 0,
        }
        result.matched.append("weekdays")
        cut(match)
    match = _DAILY_RE.search(text)
    if match:
        result.series = {"rule": "daily", "weekdays": list(range(7)), "dayOfMonth": 0}
        result.matched.append("daily")
        cut(match)

    # ---- 日期 ----
    match = _DATE_RE.search(text)
    if match:
        try:
            result.target_date = date(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            )
            result.matched.append("date")
            cut(match)
        except ValueError:
            pass
    if result.target_date is None:
        match = _MONTH_DAY_RE.search(text)
        if match:
            result.target_date = _resolve_month_day(
                today, int(match.group(1)), int(match.group(2))
            )
            result.matched.append("date")
            cut(match)
    if result.target_date is None:
        match = _OFFSET_RE.search(text)
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            if unit == "d":
                result.target_date = today + timedelta(days=amount)
            elif unit == "w":
                result.target_date = today + timedelta(days=amount * 7)
            else:
                result.target_date = today + timedelta(days=amount * 30)
            result.matched.append("date")
            cut(match)
    if result.target_date is None:
        match = _NEXT_WEEK_RE.search(text)
        if match:
            result.target_date = _next_week_day(today, match.group(1))
            result.matched.append("date")
            cut(match)
    if result.target_date is None:
        match = _DAY_WORD_RE.search(text)
        if match:
            word = match.group(0)
            offset = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}[word]
            result.target_date = today + timedelta(days=offset)
            result.matched.append("date")
            cut(match)

    # ---- 时间（@ 优先，其次中文「点」）----
    match = _TIME_COLON_RE.search(text)
    hour = minute = None
    if match:
        cut(match)
    else:
        match = _TIME_CN_RE.search(text)
        if match:
            cut(match)
    if match:
        hour = int(match.group(1))
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            minute = int(match.group(2))
        else:
            minute = 0
        if "点" in match.group(0) and match.group(0).endswith("半"):
            minute = 30
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result.remind_at = f"{hour:02d}:{minute:02d}"
            result.matched.append("time")
        else:
            result.remind_at = None

    # ---- 优先级 ----
    match = _PRIORITY_RE.search(text)
    if match:
        result.priority = 1 if len(match.group(1)) == 1 else 2
        result.matched.append("priority")
        cut(match)

    # ---- 正文 = 去掉已识别片段 ----
    kept: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        kept.append(text[cursor:start])
        cursor = max(cursor, end)
    kept.append(text[cursor:])
    body = re.sub(r"\s{2,}", " ", "".join(kept)).strip()
    body = body.strip(" ,，、;；:：")
    result.text = body[:MAX_TEXT]
    return result


def parse_reminder(value: str) -> str | None:
    """把用户输入的提醒时间规范化成 HH:MM。"""
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d{1,2})\s*[:：]\s*(\d{1,2})\s*", value)
    if not match:
        match = re.fullmatch(r"\s*(\d{1,2})\s*", value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.lastindex and match.lastindex >= 2 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"
