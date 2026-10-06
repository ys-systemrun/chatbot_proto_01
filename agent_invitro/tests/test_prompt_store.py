"""プロンプトファイルの読み込み（ADR-0099 §3）を検証する。"""

from src import prompt_store

# 回答経路と IPython 用 ReAct が読み込むプロンプト（各モジュールの load_prompt 呼び出しと対応）。
EXPECTED = {
    "generate", "condense", "summarize", "summarize_with_existing", "clarify", "assess", "react_agent",
}


def test_all_prompt_files_exist_and_are_loaded_by_modules():
    from src import clarify, condense, generate, summarize
    from src.graph import agent
    from src.llm_tasks.assess import prompts as assess_prompts

    prompts = prompt_store.all_prompts()
    assert set(prompts) == EXPECTED
    assert generate._SYSTEM_PROMPT == prompts["generate"]
    assert condense._SYSTEM_PROMPT == prompts["condense"]
    assert summarize._SYSTEM_PROMPT == prompts["summarize"]
    assert summarize._SYSTEM_PROMPT_WITH_EXISTING == prompts["summarize_with_existing"]
    assert clarify._SYSTEM_PROMPT == prompts["clarify"]
    assert assess_prompts.SYSTEM_PROMPT == prompts["assess"]
    assert agent.SYSTEM_PROMPT == prompts["react_agent"]


def test_crlf_is_normalized_and_readme_is_excluded(tmp_path):
    (tmp_path / "a.md").write_bytes("一行目\r\n二行目".encode("utf-8"))
    (tmp_path / "README.md").write_text("説明", encoding="utf-8")

    assert prompt_store.load_prompt("a", tmp_path) == "一行目\n二行目"
    assert prompt_store.all_prompts(tmp_path) == {"a": "一行目\n二行目"}


def test_hash_ignores_line_endings_but_tracks_content_and_names(tmp_path):
    lf, crlf = tmp_path / "lf", tmp_path / "crlf"
    lf.mkdir()
    crlf.mkdir()
    (lf / "a.md").write_bytes(b"x\ny")
    (crlf / "a.md").write_bytes(b"x\r\ny")
    assert prompt_store.prompts_hash(lf) == prompt_store.prompts_hash(crlf)

    base = prompt_store.prompts_hash(lf)
    (lf / "a.md").write_bytes(b"x\nz")
    assert prompt_store.prompts_hash(lf) != base
    (lf / "a.md").rename(lf / "b.md")
    assert prompt_store.prompts_hash(lf) != prompt_store.prompts_hash(crlf)


def test_directory_can_be_overridden_by_env(tmp_path, monkeypatch):
    (tmp_path / "generate.md").write_text("別の文面", encoding="utf-8")
    monkeypatch.setenv("AGENT_PROMPTS_DIR", str(tmp_path))

    assert prompt_store.load_prompt("generate") == "別の文面"
