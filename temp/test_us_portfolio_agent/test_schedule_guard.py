"""GitHub Actions 定时补跑去重逻辑的单元测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import schedule_guard as schedule_guard_script
from us_stock_agent.schedule_guard import (
    DAILY_SCHEDULES,
    WEEKLY_SCHEDULES,
    ScheduleGuardError,
    build_guard_decision,
    marker_name,
    report_type_for_schedule,
)


class TestScheduleGuard(unittest.TestCase):
    """验证自动补跑可以识别同一天已成功发送的报告。"""

    def test_report_type_for_schedule_supports_primary_and_backup_crons(self) -> None:
        """主 cron 和补跑 cron 都应映射到正确报告类型。"""
        for schedule in DAILY_SCHEDULES:
            self.assertEqual(report_type_for_schedule(schedule), "daily")

        for schedule in WEEKLY_SCHEDULES:
            self.assertEqual(report_type_for_schedule(schedule), "weekly")

    def test_marker_name_uses_beijing_date(self) -> None:
        """marker 名称应使用北京时间日期，避免 UTC 日期误判。"""
        self.assertEqual(
            marker_name("daily", "2026-07-10T00:17:00Z"),
            "us-stock-report-marker-daily-2026-07-10",
        )
        self.assertEqual(
            marker_name("weekly", "2026-07-10T16:30:00Z"),
            "us-stock-report-marker-weekly-2026-07-11",
        )

    def test_build_guard_decision_skips_when_today_marker_exists(self) -> None:
        """当天已有成功 marker 时，后续自动补跑应跳过发送。"""
        decision = build_guard_decision(
            event_name="schedule",
            schedule=DAILY_SCHEDULES[1],
            now_iso="2026-07-10T00:37:00Z",
            artifact_names=["us-stock-report-marker-daily-2026-07-10"],
        )

        self.assertTrue(decision.skip)
        self.assertEqual(decision.report_type, "daily")
        self.assertEqual(decision.marker, "us-stock-report-marker-daily-2026-07-10")

    def test_build_guard_decision_does_not_skip_without_today_marker(self) -> None:
        """没有当天 marker 时，自动补跑应继续执行报告。"""
        decision = build_guard_decision(
            event_name="schedule",
            schedule=DAILY_SCHEDULES[1],
            now_iso="2026-07-10T00:37:00Z",
            artifact_names=["us-stock-report-marker-daily-2026-07-09"],
        )

        self.assertFalse(decision.skip)
        self.assertEqual(decision.report_type, "daily")

    def test_workflow_dispatch_dedupes_when_requested(self) -> None:
        """外部补发请求应在当天已有 marker 时跳过重复邮件。"""
        decision = build_guard_decision(
            event_name="workflow_dispatch",
            report_type="daily",
            manual_deduplication=True,
            now_iso="2026-07-16T01:05:00Z",
            artifact_names=["us-stock-report-marker-daily-2026-07-16"],
        )

        self.assertTrue(decision.skip)
        self.assertEqual(decision.marker, "us-stock-report-marker-daily-2026-07-16")
        self.assertIn("当天已有成功 marker", decision.reason)

    def test_script_accepts_deduplicated_external_dispatch(self) -> None:
        """补发脚本应向 artifact 查询函数传递具名事件上下文。"""
        outputs: dict[str, str] = {}

        def fetch_artifact_names(*, event_name: str, manual_deduplication: bool) -> list[str]:
            self.assertEqual(event_name, "workflow_dispatch")
            self.assertTrue(manual_deduplication)
            return []

        with patch.dict(
            "os.environ",
            {
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "WORKFLOW_REPORT_TYPE": "daily",
                "WORKFLOW_DEDUPE_MANUAL": "true",
            },
            clear=True,
        ):
            with patch.object(schedule_guard_script, "_utc_now_iso", return_value="2026-07-16T01:05:00Z"):
                with patch.object(
                    schedule_guard_script,
                    "_fetch_artifact_names_for_event",
                    side_effect=fetch_artifact_names,
                ):
                    with patch.object(schedule_guard_script, "_write_outputs", side_effect=outputs.update):
                        self.assertEqual(schedule_guard_script.main(), 0)

        self.assertEqual(outputs["skip"], "false")
        self.assertEqual(outputs["report_type"], "daily")

    def test_unknown_schedule_fails_explicitly(self) -> None:
        """未知 cron 不应被静默当成日报或周报。"""
        with self.assertRaises(ScheduleGuardError):
            build_guard_decision(
                event_name="schedule",
                schedule="0 0 * * *",
                now_iso="2026-07-10T00:00:00Z",
                artifact_names=[],
            )

    def test_workflow_contains_guard_and_declared_crons(self) -> None:
        """workflow 文件应同步声明 guard 使用的所有 cron。"""
        workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "us-stock-report.yml"
        content = workflow.read_text(encoding="utf-8")

        for schedule in (*DAILY_SCHEDULES, *WEEKLY_SCHEDULES):
            self.assertIn(f'cron: "{schedule}"', content)
        self.assertIn("dedupe:", content)
        self.assertIn("WORKFLOW_DEDUPE_MANUAL", content)
        self.assertIn("python scripts/schedule_guard.py", content)
        self.assertIn("Upload report marker", content)


if __name__ == "__main__":
    unittest.main()
