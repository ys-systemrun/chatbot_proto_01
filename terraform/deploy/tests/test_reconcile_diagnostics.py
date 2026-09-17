"""Service Connect 整合の待機失敗時に、一次情報を出し切ることを検証する。

boto3 の「Max attempts exceeded」だけでは、どのサービスが不安定だったのか、
なぜコンテナが落ちたのかが分からない（実際に tag_selector_mcp の起動時クラッシュを
agent_invitro の問題と誤認させた）。実 AWS には触れず、aws モジュールを stub して
警告文と診断呼び出しを確認する。
"""

import time

import pytest

from src import aws, commands
from src.errors import ServicesNotStable


class _FakeEcs:
    """describe_services が呼ばれるたびに用意した応答を順に返す stub。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def describe_services(self, cluster, services):
        self.calls.append((cluster, tuple(services)))
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


def _svc(name, desired=1, running=1, pending=0, deployments=1):
    return {
        "serviceName": name,
        "desiredCount": desired,
        "runningCount": running,
        "pendingCount": pending,
        "deployments": [{"status": "PRIMARY"}] * deployments,
    }


def test_wait_services_stable_returns_when_all_steady(monkeypatch):
    fake = _FakeEcs([{"services": [_svc("knowledge_mcp"), _svc("tag_selector_mcp")]}])
    monkeypatch.setattr(aws, "_client", lambda *a, **k: fake)

    aws.wait_services_stable("cl", ["knowledge_mcp", "tag_selector_mcp"], "us-east-1")

    assert fake.calls == [("cl", ("knowledge_mcp", "tag_selector_mcp"))]


def test_wait_services_stable_names_the_unstable_service(monkeypatch):
    fake = _FakeEcs(
        [
            {
                "services": [
                    _svc("knowledge_mcp"),
                    _svc("tag_selector_mcp", running=0, pending=1),
                ]
            }
        ]
    )
    monkeypatch.setattr(aws, "_client", lambda *a, **k: fake)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    with pytest.raises(ServicesNotStable) as excinfo:
        aws.wait_services_stable(
            "cl", ["knowledge_mcp", "tag_selector_mcp"], "us-east-1",
            timeout_sec=30, interval_sec=15,
        )

    # knowledge_mcp は安定しているので名指ししない。
    assert excinfo.value.services == ["tag_selector_mcp"]
    assert "tag_selector_mcp" in str(excinfo.value)


def test_reconcile_reports_stopped_reason_and_logs(monkeypatch, capsys):
    """待機が落ちたら、不安定なサービス名・stopCode/exitCode・コンテナログを出す。"""
    monkeypatch.setattr(
        commands.aws,
        "wait_services_stable",
        lambda *a, **k: (_ for _ in ()).throw(
            ServicesNotStable(["tag_selector_mcp"], 600)
        ),
    )
    monkeypatch.setattr(
        commands.aws,
        "describe_service_health",
        lambda c, s, r: [
            {
                "name": "tag_selector_mcp",
                "desired": 1,
                "running": 0,
                "pending": 1,
                "rollout": "IN_PROGRESS",
                "rollout_reason": "rolling out",
                "events": ["service tag_selector_mcp has started 1 tasks"],
            }
        ],
    )
    monkeypatch.setattr(
        commands.aws,
        "recent_stopped_tasks",
        lambda c, s, r: [
            {
                "task_arn": "arn:aws:ecs:us-east-1:1:task/cl/abc",
                "stop_code": "EssentialContainerExited",
                "stopped_reason": "Essential container in task exited",
                "stopped_at": "2026-09-16T17:04:54",
                "containers": [
                    {"name": "tag_selector_mcp", "exit_code": 1, "reason": None}
                ],
            }
        ],
    )
    monkeypatch.setattr(
        commands.aws,
        "get_task_log_events",
        lambda *a, **k: ["Traceback (most recent call last):", "UndefinedTable: tag"],
    )

    commands._reconcile_agent_after_servers("cl", "us-east-1")

    out = capsys.readouterr().out
    # 「agent_invitro の再デプロイ失敗」と決め打ちせず、実際の犯人を名指しする。
    assert "tag_selector_mcp" in out
    assert "EssentialContainerExited" in out
    assert "exitCode=1" in out
    assert "UndefinedTable: tag" in out
    # 手動コマンドの案内には --region が付く。
    assert "--region us-east-1" in out


def test_reconcile_survives_diagnostics_failure(monkeypatch, capsys):
    """診断自体が失敗しても、元の警告は残り例外は伝播しない。"""
    monkeypatch.setattr(
        commands.aws,
        "wait_services_stable",
        lambda *a, **k: (_ for _ in ()).throw(ServicesNotStable(["knowledge_mcp"], 600)),
    )
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("AccessDenied"))
    monkeypatch.setattr(commands.aws, "describe_service_health", boom)
    monkeypatch.setattr(commands.aws, "recent_stopped_tasks", boom)

    commands._reconcile_agent_after_servers("cl", "us-east-1")

    out = capsys.readouterr().out
    assert "Service Connect 整合処理が失敗" in out
    assert "AccessDenied" in out
