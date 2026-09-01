#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FOLIA_DIR="${ROOT_DIR}/.work/Folia"
POST_PATCH_DIR="${ROOT_DIR}/neverfolia-patches/post-apply"
HELPER_FILE="${FOLIA_DIR}/folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement.java"

if [ ! -d "${FOLIA_DIR}" ]; then
  echo "[NeverFolia] Folia worktree not found: ${FOLIA_DIR}" >&2
  exit 2
fi

echo "[NeverFolia] Applying NeverNether native placement hook"
python3 "${ROOT_DIR}/scripts/apply-never-nether-placement-hook.py" "${FOLIA_DIR}"

# Minecraft 26.2 renamed ResourceKey#location() to ResourceKey#identifier().
# Keep this explicit compatibility normalization until the transformer is promoted
# to a conventional post-apply source patch after TEST1 stabilizes.
sed -i 's/key\.location()/key.identifier()/g' "${HELPER_FILE}"
if grep -q 'key\.location()' "${HELPER_FILE}"; then
  echo "[NeverFolia] Failed to normalize ResourceKey API in placement helper" >&2
  exit 3
fi

echo "[NeverFolia] Adding optional NeverNether placement diagnostics"
python3 "${ROOT_DIR}/scripts/instrument-never-nether-placement-debug.py" "${FOLIA_DIR}"

if ! compgen -G "${POST_PATCH_DIR}/*.patch" > /dev/null; then
  echo "[NeverFolia] No additional post-apply patch files"
  exit 0
fi

cd "${FOLIA_DIR}"
echo "[NeverFolia] Applying post-apply patch files"
for patch_file in "${POST_PATCH_DIR}"/*.patch; do
  echo "  -> $(basename "${patch_file}")"
  git apply --whitespace=nowarn "${patch_file}"
done
