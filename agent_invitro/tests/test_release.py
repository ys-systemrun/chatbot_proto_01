"""リリース（ADR-0099 §1）の算出と assistant メッセージへの付与を検証する。"""

from src import release
from src.config import Settings
from src.usecases import conversation


def _settings(**overrides):
    base = dict(
        knowledge_mcp_url="http://k",
        tag_selector_mcp_url="http://t",
        llm_provider="bedrock",
        bedrock_chat_model_id="model-a",
        bedrock_region="us-east-1",
    )
    base.update(overrides)
    return Settings(**base)


ENV = {"GIT_COMMIT": "abc123", "GIT_DIRTY": "false", "BEDROCK_EMBEDDING_MODEL_ID": "emb-1"}


def test_release_contains_all_components():
    r = release.build_release(_settings(), env=ENV)

    assert r["git_commit"] == "abc123"
    assert r["git_dirty"] is False
    assert r["chat_model_id"] == "model-a"
    assert r["embedding_model_id"] == "emb-1"
    assert len(r["prompt_hash"]) == 16
    assert r["params"]["temperature"] == 0
    assert r["params"]["agentic_max_iterations"] == 2
    assert len(r["release_id"]) == 16


def test_release_id_is_stable_for_same_configuration():
    assert release.build_release(_settings(), env=ENV)["release_id"] == (
        release.build_release(_settings(), env=ENV)["release_id"]
    )


def test_release_id_changes_with_model_params_or_commit():
    base = release.build_release(_settings(), env=ENV)["release_id"]

    assert release.build_release(_settings(bedrock_chat_model_id="model-b"), env=ENV)["release_id"] != base
    assert release.build_release(_settings(agentic_search_top_k=5), env=ENV)["release_id"] != base
    assert release.build_release(_settings(), env={**ENV, "GIT_COMMIT": "def456"})["release_id"] != base


def test_unset_git_env_is_recorded_as_unknown():
    r = release.build_release(_settings(), env={})

    assert r["git_commit"] is None
    assert r["git_dirty"] is None


def test_release_id_changes_when_a_prompt_file_changes(tmp_path, monkeypatch):
    from src import prompt_store

    for name, text in prompt_store.all_prompts().items():
        (tmp_path / f"{name}.md").write_text(text, encoding="utf-8")
    monkeypatch.setenv("AGENT_PROMPTS_DIR", str(tmp_path))
    before = release.build_release(_settings(), env=ENV)

    (tmp_path / "generate.md").write_text(prompt_store.load_prompt("generate") + "追記", encoding="utf-8")
    after = release.build_release(_settings(), env=ENV)

    # 同じ文面なら既定ディレクトリ（agent_invitro/prompts/）と同じハッシュになる。
    assert before["prompt_hash"] == prompt_store.prompts_hash(prompt_store._DEFAULT_DIR)
    assert after["prompt_hash"] != before["prompt_hash"]
    assert after["release_id"] != before["release_id"]


def test_assistant_message_carries_release_and_mode():
    components = {"release": {"release_id": "r1"}}

    msg = conversation.build_assistant_message(
        2, "answer", "prompt", "model-a",
        release_id=conversation.release_id_of(components), ask_mode="agentic",
    )

    assert msg.release_id == "r1"
    assert msg.ask_mode == "agentic"
    assert msg.evaluation == 0
    assert conversation.release_id_of({}) is None
