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

echo "[NeverFolia] Applying NeverNether Basalt Columns chunk ownership hook"
python3 "${ROOT_DIR}/scripts/apply-never-nether-basalt-columns-ownership.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverNether NetherrackReplaceBlobs chunk ownership hook"
python3 "${ROOT_DIR}/scripts/apply-never-nether-netherrack-blobs-ownership.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld native lava-free aquifer picker"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-fluid-picker.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld native generated-fluid feature filter"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-fluid-feature-filter.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld SeagrassFeature chunk ownership hook"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-seagrass-ownership.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld native deterministic ore geology"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-ore-geology.py" "${FOLIA_DIR}"

# Folia 26.2 uses Moonrise's ChunkLightTask as the actual LIGHT runtime path.
# The vanilla ChunkStatusTasks.light(...) method still compiles but is bypassed by
# the Moonrise chunk scheduler, so the flood barrier must live in ChunkLightTask.
echo "[NeverFolia] Applying NeverOverworld Moonrise LIGHT flood barrier"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-moonrise-light-flood-hook.py" "${FOLIA_DIR}"

# Radius-1 FEATURES may race with the owning chunk's Moonrise LIGHT task. Make
# dry replaceable decorations part of the floodable volume so final geometry is
# independent from whether vegetation/leaf litter arrived immediately before or
# after the flood pass.
echo "[NeverFolia] Applying NeverOverworld deterministic floodable-volume semantics"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-floodable-volume.py" "${FOLIA_DIR}"

echo "[NeverFolia] Instrumenting NeverOverworld LIGHT flood activation"
python3 "${ROOT_DIR}/scripts/instrument-never-overworld-flood-debug.py" "${FOLIA_DIR}"

echo "[NeverFolia] Adding optional NeverNether placement diagnostics"
python3 "${ROOT_DIR}/scripts/instrument-never-nether-placement-debug.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverNether startup fingerprint guard"
python3 "${ROOT_DIR}/scripts/apply-never-nether-fingerprint-guard.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld startup fingerprint guard"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-fingerprint-guard.py" "${FOLIA_DIR}"

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
