"""自然语言快速添加的解析测试（纯函数，不需要 Qt）。"""

from __future__ import annotations

import unittest
from datetime import date

from tests import *  # noqa: F401,F403 - 负责 sys.path 注入
from app.quickadd import (
    MAX_TEXT,
    ParsedQuickAdd,
    describe_series,
    format_day,
    parse_quick_add,
    parse_reminder,
)

TODAY = date(2026, 10, 30)  # 周五


class ParseQuickAddTests(unittest.TestCase):
    def parse(self, raw: str) -> ParsedQuickAdd:
        return parse_quick_add(raw, today=TODAY)

    def test_plain_text(self) -> None:
        parsed = self.parse("买牛奶")
        self.assertEqual(parsed.text, "买牛奶")
        self.assertIsNone(parsed.target_date)
        self.assertIsNone(parsed.remind_at)
        self.assertEqual(parsed.priority, 0)
        self.assertIsNone(parsed.series)
        self.assertFalse(parsed.is_empty)

    def test_empty(self) -> None:
        parsed = self.parse("   ")
        self.assertTrue(parsed.is_empty)
        self.assertEqual(parsed.text, "")
        self.assertEqual(parsed.summary(), "")

    def test_tomorrow_time_and_priority(self) -> None:
        parsed = self.parse("明天 @15:00 交报告 !!")
        self.assertEqual(parsed.target_date, date(2026, 10, 31))
        self.assertEqual(parsed.remind_at, "15:00")
        self.assertEqual(parsed.priority, 2)
        self.assertEqual(parsed.text, "交报告")

    def test_colloquial_time(self) -> None:
        parsed = self.parse("后天 @9点半 开会")
        self.assertEqual(parsed.target_date, date(2026, 11, 1))
        self.assertEqual(parsed.remind_at, "09:30")
        self.assertEqual(parsed.text, "开会")

    def test_month_day(self) -> None:
        self.assertEqual(self.parse("10月30日 复盘").target_date, date(2026, 10, 30))
        self.assertEqual(self.parse("11月1号 体检").target_date, date(2026, 11, 1))

    def test_iso_date(self) -> None:
        parsed = self.parse("2026-11-05 体检")
        self.assertEqual(parsed.target_date, date(2026, 11, 5))
        self.assertEqual(parsed.text, "体检")

    def test_offsets(self) -> None:
        self.assertEqual(self.parse("+3d 回访").target_date, date(2026, 11, 2))
        self.assertEqual(self.parse("+2w 复盘").target_date, date(2026, 11, 13))

    def test_day_words(self) -> None:
        self.assertEqual(self.parse("今天 写周报").target_date, date(2026, 10, 30))
        self.assertEqual(self.parse("明天 写周报").target_date, date(2026, 10, 31))
        self.assertEqual(self.parse("后天 写周报").target_date, date(2026, 11, 1))
        self.assertEqual(self.parse("大后天 出差").target_date, date(2026, 11, 2))
        self.assertEqual(self.parse("大后天 出差").text, "出差")

    def test_next_week(self) -> None:
        # 2026-10-30 是周五，下一个周一 = 11-02
        self.assertEqual(self.parse("下周一 台账").target_date, date(2026, 11, 2))
        self.assertEqual(self.parse("下周三 例会").target_date, date(2026, 11, 4))

    def test_series_rules(self) -> None:
        daily = self.parse("~每天 吃药")
        self.assertEqual(daily.series["rule"], "daily")
        self.assertEqual(daily.series["weekdays"], list(range(7)))
        self.assertEqual(daily.text, "吃药")

        weekdays = self.parse("~工作日 站会")
        self.assertEqual(weekdays.series["rule"], "weekdays")
        self.assertEqual(weekdays.series["weekdays"], [0, 1, 2, 3, 4])

        weekly = self.parse("~每周三 例会")
        self.assertEqual(weekly.series["rule"], "weekly")
        self.assertEqual(weekly.series["weekdays"], [2])

        monthly = self.parse("~每月1日 交房租")
        self.assertEqual(monthly.series["rule"], "monthly")
        self.assertEqual(monthly.series["dayOfMonth"], 1)

    def test_combined(self) -> None:
        parsed = self.parse("~每周一 @8点 !! 站会")
        self.assertEqual(parsed.series["rule"], "weekly")
        self.assertEqual(parsed.priority, 2)
        self.assertEqual(parsed.remind_at, "08:00")
        self.assertEqual(parsed.text, "站会")

    def test_summary_text(self) -> None:
        parsed = self.parse("明天 @15:00 交报告 !!")
        summary = parsed.summary()
        self.assertIn("明天", summary)
        self.assertIn("15:00", summary)
        self.assertIn("紧急", summary)

    def test_text_is_truncated(self) -> None:
        parsed = self.parse("任" * (MAX_TEXT + 50))
        self.assertEqual(len(parsed.text), MAX_TEXT)

    def test_unmatched_noise_is_kept_as_body(self) -> None:
        parsed = self.parse("给王工回电话 关于预算")
        self.assertEqual(parsed.text, "给王工回电话 关于预算")


class HelperTests(unittest.TestCase):
    def test_format_day(self) -> None:
        self.assertEqual(format_day(TODAY, TODAY), "今天")
        self.assertEqual(format_day(date(2026, 10, 31), TODAY), "明天")
        self.assertEqual(format_day(date(2026, 11, 1), TODAY), "后天")
        self.assertEqual(format_day(date(2026, 10, 29), TODAY), "昨天")
        self.assertEqual(format_day(date(2026, 11, 3), TODAY), "周二")
        self.assertEqual(format_day(date(2026, 12, 24), TODAY), "12月24日")
        self.assertEqual(format_day(date(2027, 1, 5), TODAY), "2027年1月5日")

    def test_parse_reminder(self) -> None:
        self.assertEqual(parse_reminder("9"), "09:00")
        self.assertEqual(parse_reminder("9:30"), "09:30")
        self.assertEqual(parse_reminder(" 21：05 "), "21:05")
        self.assertIsNone(parse_reminder("25:00"))
        self.assertIsNone(parse_reminder("abc"))
        self.assertIsNone(parse_reminder(""))

    def test_describe_series(self) -> None:
        self.assertEqual(describe_series({"rule": "daily", "weekdays": []}), "每天")
        self.assertEqual(describe_series({"rule": "weekly", "weekdays": [2]}), "每周三")
        self.assertEqual(describe_series({"rule": "monthly", "dayOfMonth": 5}), "每月5日")
        self.assertEqual(describe_series({"rule": "weekdays"}), "工作日")


if __name__ == "__main__":
    unittest.main()
