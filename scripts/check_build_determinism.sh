#!/usr/bin/env bash
# Build the same commit twice and assert resolved Python + Node dependency sets match.
# Emits compared sets under artifacts/build-determinism/.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${BUILD_DETERMINISM_OUT:-artifacts/build-determinism}"
mkdir -p "${OUT}"
TAG_A="heatguard:det-a-$$"
TAG_B="heatguard:det-b-$$"
cleanup() {
  docker rmi -f "${TAG_A}" "${TAG_B}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Build A"
docker build --no-cache -t "${TAG_A}" .
echo "==> Build B"
docker build --no-cache -t "${TAG_B}" .

extract_python() {
  local tag="$1" dest="$2"
  docker run --rm --entrypoint python "${tag}" - <<'PY' >"${dest}"
from importlib.metadata import distributions
rows = sorted(
    f"{d.metadata['Name'].lower()}=={d.version}"
    for d in distributions()
    if d.metadata.get("Name")
)
print("\n".join(rows))
PY
}

extract_npm() {
  local tag="$1" dest="$2"
  docker run --rm --entrypoint cat "${tag}" /app/.build-meta/npm-deps.txt >"${dest}"
}

extract_python "${TAG_A}" "${OUT}/python-a.txt"
extract_python "${TAG_B}" "${OUT}/python-b.txt"
extract_npm "${TAG_A}" "${OUT}/npm-a.txt"
extract_npm "${TAG_B}" "${OUT}/npm-b.txt"

cp "${OUT}/python-a.txt" "${OUT}/python-set.txt"
cp "${OUT}/npm-a.txt" "${OUT}/npm-set.txt"

fail=0
if ! diff -u "${OUT}/python-a.txt" "${OUT}/python-b.txt" >"${OUT}/python.diff"; then
  echo "FAIL — Python dependency sets differ between successive builds"
  cat "${OUT}/python.diff"
  fail=1
else
  echo "OK — Python dependency sets identical"
  : >"${OUT}/python.diff"
fi

if ! diff -u "${OUT}/npm-a.txt" "${OUT}/npm-b.txt" >"${OUT}/npm.diff"; then
  echo "FAIL — npm dependency sets differ between successive builds"
  cat "${OUT}/npm.diff"
  fail=1
else
  echo "OK — npm dependency sets identical"
  : >"${OUT}/npm.diff"
fi

exit "${fail}"
