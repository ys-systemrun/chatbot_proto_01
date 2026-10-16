# 評価ランナー（ADR-0099 §5）のイメージ。eval.bat が毎回 build する（変更が無ければキャッシュで即時）。
# ランナー本体はイメージに焼き込まず、リポジトリを /work にマウントして実行する。
FROM python:3.11-slim

# LLM 採点（Amazon Bedrock 上の Claude）を Anthropic SDK の Bedrock Mantle クライアントで呼ぶ。
ARG ANTHROPIC_VERSION=1.11.0
RUN pip install --no-cache-dir "anthropic[bedrock]==${ANTHROPIC_VERSION}"

# LLM 採点を Claude Code の非対話モード（claude -p、サブスクリプション認証）でも行えるようにする（ADR-0101）。
# 公式のネイティブインストーラで入れる。CLAUDE_CODE_VERSION に版（例: 2.1.289）を指定すると固定できる。
# 実際に使った版は採点のたびに meta.json の judge.cli_version に記録する。自動更新は止める。
ARG CLAUDE_CODE_VERSION=stable
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://claude.ai/install.sh | bash -s "${CLAUDE_CODE_VERSION}"

ENV PATH=/root/.local/bin:$PATH DISABLE_AUTOUPDATER=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
