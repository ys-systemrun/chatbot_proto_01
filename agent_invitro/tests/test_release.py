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


def test_prompt_hash_covers_answer_path_prompts():
    texts = release._prompt_texts()

    for key in ("generate._SYSTEM_PROMPT", "condense._SYSTEM_PROMPT", "summarize._SYSTEM_PROMPT",
                "summarize._SYSTEM_PROMPT_WITH_EXISTING", "clarify._SYSTEM_PROMPT",
                "assess.ASSESS_SYSTEM_PROMPT"):
        assert key in texts
    changed = {**texts, "generate._SYSTEM_PROMPT": texts["generate._SYSTEM_PROMPT"] + "x"}
    assert release.prompt_hash(changed) != release.prompt_hash(texts)


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
