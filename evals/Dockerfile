# 評価ランナー（ADR-0099 §5）のイメージ。eval.bat が毎回 build する（変更が無ければキャッシュで即時）。
# ランナー本体はイメージに焼き込まず、リポジトリを /work にマウントして実行する。
FROM python:3.11-slim

# LLM 採点（Amazon Bedrock 上の Claude）を Anthropic SDK の Bedrock Mantle クライアントで呼ぶ。
ARG ANTHROPIC_VERSION=1.11.0
RUN pip install --no-cache-dir "anthropic[bedrock]==${ANTHROPIC_VERSION}"

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
