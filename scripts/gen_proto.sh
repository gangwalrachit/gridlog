#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/gridlog/grpc_service/generated"

mkdir -p "${OUT_DIR}"

python -m grpc_tools.protoc \
  -I "${REPO_ROOT}/proto" \
  --python_out="${OUT_DIR}" \
  --grpc_python_out="${OUT_DIR}" \
  "${REPO_ROOT}/proto/prices.proto"

touch "${OUT_DIR}/__init__.py"

echo "Proto generated → ${OUT_DIR}"
