#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${ROOT_DIR}/.work"
FOLIA_DIR="${WORK_DIR}/Folia"

set -a
source "${ROOT_DIR}/build.env"
set +a

rm -rf "${FOLIA_DIR}"
mkdir -p "${WORK_DIR}"

echo "[NeverFolia] Cloning ${FOLIA_REPOSITORY}@${FOLIA_REF}"
git clone --depth 1 --branch "${FOLIA_REF}" "https://github.com/${FOLIA_REPOSITORY}.git" "${FOLIA_DIR}"

cd "${FOLIA_DIR}"

python3 - <<'PY'
from pathlib import Path

settings = Path("settings.gradle.kts")
text = settings.read_text(encoding="utf-8")
text = text.replace('rootProject.name = "folia"', 'rootProject.name = "neverfolia"')
settings.write_text(text, encoding="utf-8")

patch = Path("folia-server/build.gradle.kts.patch")
text = patch.read_text(encoding="utf-8")
replacements = {
    '+            "Implementation-Title" to "Folia",': '+            "Implementation-Title" to "NeverFolia",',
    '+            "Specification-Title" to "Folia",': '+            "Specification-Title" to "NeverFolia",',
    '+            "Brand-Id" to "papermc:folia",': '+            "Brand-Id" to "neverland:neverfolia",',
    '+            "Brand-Name" to "Folia",': '+            "Brand-Name" to "NeverFolia",',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"Required branding marker not found: {old}")
    text = text.replace(old, new)
patch.write_text(text, encoding="utf-8")
PY

# Future NeverFolia source patches are applied here after the Folia base is prepared.
# This directory is intentionally optional during bootstrap.
if compgen -G "${ROOT_DIR}/neverfolia-patches/*.patch" > /dev/null; then
  echo "[NeverFolia] Applying NeverFolia repository patches"
  for patch_file in "${ROOT_DIR}"/neverfolia-patches/*.patch; do
    echo "  -> $(basename "${patch_file}")"
    git apply --whitespace=nowarn "${patch_file}"
  done
fi

echo "[NeverFolia] Upstream prepared at ${FOLIA_DIR}"
