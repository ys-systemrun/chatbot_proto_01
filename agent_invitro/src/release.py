"""リリース（回答を生成した構成の版）の算出（ADR-0099 §1）。

リリースは「コードの版・プロンプトの版・モデル・回答に効く設定値」の組で、`release_id` はそれを
正規化した JSON の SHA-256 の先頭16桁。同じ構成なら同じ ID になるため、再デプロイ・再起動では増えない。

- git_commit / git_dirty: デプロイ時に deploy が GIT_COMMIT / GIT_DIRTY 環境変数で渡す（ローカルは未設定）
- prompt_hash: agent_invitro/prompts/ のプロンプト一式の内容ハッシュ（ADR-0099 §3, prompt_store）
- chat_model_id / embedding_model_id: Bedrock のモデル ID
- params: 回答に効く設定値

本モジュールは fastapi に依存しない（ADR-0090 決定4）。
"""

from __future__ import annotations

import hashlib
import json
import os

from .config import Settings
from .prompt_store import prompts_hash

# llm.py の ChatBedrockConverse / 各 *LLMBedrock は temperature=0 固定。
_TEMPERATURE = 0


def build_release(settings: Settings, env: dict[str, str] | None = None) -> dict:
    """リリースの全要素と release_id を返す。"""
    env = os.environ if env is None else env
    components = {
        "git_commit": env.get("GIT_COMMIT", "") or None,
        "git_dirty": (env.get("GIT_DIRTY", "").lower() == "true") if env.get("GIT_DIRTY") else None,
        "prompt_hash": prompts_hash(),
        "chat_model_id": settings.bedrock_chat_model_id or settings.lmstudio_chat_model,
        "embedding_model_id": env.get("BEDROCK_EMBEDDING_MODEL_ID", "") or None,
        "params": {
            "temperature": _TEMPERATURE,
            "tag_selector_max_tags": settings.tag_selector_max_tags,
            "tag_selector_confidence_threshold": settings.tag_selector_confidence_threshold,
            "agentic_max_iterations": settings.agentic_max_iterations,
            "agentic_search_top_k": settings.agentic_search_top_k,
        },
    }
    canonical = json.dumps(components, ensure_ascii=False, sort_keys=True)
    release_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {"release_id": release_id, **components}
