#!/usr/bin/env bash
# Regenerate gRPC Python stubs from proto/ into gridlog/grpc_service/generated/.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/gridlog/grpc_service/generated"

mkdir -p "${OUT_DIR}"

python -m grpc_tools.protoc \
  -I "${REPO_ROOT}/proto" \
  --python_out="${OUT_DIR}" \
  --grpc_python_out="${OUT_DIR}" \
  --pyi_out="${OUT_DIR}" \
  "${REPO_ROOT}/proto/prices.proto"

# grpc_tools emits a top-level `import prices_pb2` in prices_pb2_grpc.py, which
# only resolves when the output dir is on sys.path. Rewrite to a relative import
# so `gridlog.grpc_service.generated` works as a proper package.
sed -i.bak 's/^import prices_pb2/from . import prices_pb2/' "${OUT_DIR}/prices_pb2_grpc.py"
rm "${OUT_DIR}/prices_pb2_grpc.py.bak"

touch "${OUT_DIR}/__init__.py"

echo "Proto generated → ${OUT_DIR}"
