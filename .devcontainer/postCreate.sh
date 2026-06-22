#!/usr/bin/env bash
set -e

echo "==> Installing app dependencies..."
sudo rm -rf app/chatbot_invitro.egg-info
cd app && pip install -e . && cd ..

echo "==> Installing frontend dependencies..."
sudo chown -R "$(whoami):" front_dev/node_modules
cd front_dev && npm install --legacy-peer-deps && cd ..

echo "==> Setting up Go environment..."
cd data && go env -w GONOSUMDB="*" GOFLAGS="-mod=mod" && go mod tidy && cd ..

echo "==> Dev environment ready."
