# デプロイオーケストレータのイメージ（ADR-0040）。
# python + terraform(ピン) + docker CLI(client) を同梱。実行系をこのイメージに固定し、
# ホストは Docker Desktop だけあればよい（terraform/aws CLI のホスト導入は不要）。
FROM python:3.11-slim

# ホストの terraform と揃える（host: v1.15.7）。更新時はここを上げる。
ARG TERRAFORM_VERSION=1.15.7
# docker CLI は client のみ。ホストの Docker デーモンをソケット共有で駆動する（DooD）。
ARG DOCKER_VERSION=27.3.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates bash \
    && rm -rf /var/lib/apt/lists/*

# Terraform（ピン留め）
RUN curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -o /tmp/tf.zip \
    && unzip -o /tmp/tf.zip -d /usr/local/bin \
    && rm /tmp/tf.zip \
    && terraform version

# Docker CLI（static binary の client のみ）
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp docker/docker \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz \
    && docker --version

WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --no-cache-dir .

# provider プラグインは名前付きボリュームにキャッシュ（実行時に -v でマウント）。
ENV PYTHONUNBUFFERED=1 \
    TF_PLUGIN_CACHE_DIR=/root/.terraform.d/plugin-cache
RUN mkdir -p /root/.terraform.d/plugin-cache

# pip install で作られる `deploy` コンソールスクリプトを起動（cwd 非依存）。
ENTRYPOINT ["deploy"]
