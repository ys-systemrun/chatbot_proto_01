"""集約サービス（ADR-0095）の安定待機失敗時に、一次情報を出し切ることを検証する。

boto3 の「Max attempts exceeded」だけでは、どのサービスが不安定だったのか、
なぜコンテナが落ちたのかが分からない（実際に tag_selector_mcp の起動時クラッシュを
agent_invitro の問題と誤認させた）。4コンテナを1タスクに集約した後は「どのコンテナが
落ちたか」を名指しする必要がある。実 AWS には触れず、aws モジュールを stub して
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


def _stopped_task():
    # tag_selector_mcp が起動時に落ち、dependsOn 待ちの agent_invitro / admin_ui は未起動（exitCode=None）。
    return [
        {
            "task_arn": "arn:aws:ecs:us-east-1:1:task/cl/abc",
            "stop_code": "EssentialContainerExited",
            "stopped_reason": "Essential container in task exited",
            "stopped_at": "2026-09-16T17:04:54",
            "containers": [
                {"name": "tag_selector_mcp", "exit_code": 1, "reason": None},
                {"name": "knowledge_mcp", "exit_code": 137, "reason": None},
                {"name": "agent_invitro", "exit_code": None, "reason": None},
                {"name": "admin_ui", "exit_code": None, "reason": None},
            ],
        }
    ]


def test_wait_app_stable_reports_failed_container_and_logs(monkeypatch, capsys):
    """待機が落ちたら、stopCode/exitCode と、異常終了したコンテナのログだけを出す。"""
    monkeypatch.setattr(
        commands.aws,
        "wait_services_stable",
        lambda *a, **k: (_ for _ in ()).throw(ServicesNotStable(["prefix-app"], 600)),
    )
    monkeypatch.setattr(
        commands.aws,
        "describe_service_health",
        lambda c, s, r: [
            {
                "name": "prefix-app",
                "desired": 1,
                "running": 0,
                "pending": 1,
                "rollout": "IN_PROGRESS",
                "rollout_reason": "rolling out",
                "events": ["service prefix-app has started 1 tasks"],
            }
        ],
    )
    monkeypatch.setattr(commands.aws, "recent_stopped_tasks", lambda c, s, r: _stopped_task())
    log_calls = []

    def _logs(log_group, stream_prefix, container_name, task_arn, region):
        log_calls.append((log_group, stream_prefix, container_name))
        return {
            "tag_selector_mcp": ["Traceback (most recent call last):", "UndefinedTable: tag"],
            "knowledge_mcp": ["SIGTERM received"],
        }[container_name]

    monkeypatch.setattr(commands.aws, "get_task_log_events", _logs)

    commands._wait_app_stable("cl", "prefix-app", "us-east-1")

    out = capsys.readouterr().out
    assert "EssentialContainerExited" in out
    assert "tag_selector_mcp: exitCode=1" in out
    assert "UndefinedTable: tag" in out
    # ログはコンテナ単位のロググループ（/ecs/<container>）から、異常終了したコンテナ分だけ取る。
    assert log_calls == [
        ("/ecs/tag_selector_mcp", "tag_selector_mcp", "tag_selector_mcp"),
        ("/ecs/knowledge_mcp", "knowledge_mcp", "knowledge_mcp"),
    ]
    # 手動コマンドの案内には集約サービス名と --region が付く。
    assert "--service prefix-app" in out
    assert "--region us-east-1" in out


def test_wait_app_stable_survives_diagnostics_failure(monkeypatch, capsys):
    """診断自体が失敗しても、元の警告は残り例外は伝播しない。"""
    monkeypatch.setattr(
        commands.aws,
        "wait_services_stable",
        lambda *a, **k: (_ for _ in ()).throw(ServicesNotStable(["prefix-app"], 600)),
    )
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("AccessDenied"))
    monkeypatch.setattr(commands.aws, "describe_service_health", boom)
    monkeypatch.setattr(commands.aws, "recent_stopped_tasks", boom)

    commands._wait_app_stable("cl", "prefix-app", "us-east-1")

    out = capsys.readouterr().out
    assert "集約サービスの安定待機が失敗" in out
    assert "AccessDenied" in out


def test_wait_app_stable_ok_does_not_warn(monkeypatch, capsys):
    monkeypatch.setattr(commands.aws, "wait_services_stable", lambda *a, **k: None)

    commands._wait_app_stable("cl", "prefix-app", "us-east-1")

    out = capsys.readouterr().out
    assert "失敗" not in out
