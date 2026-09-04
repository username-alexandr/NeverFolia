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
sed -i 's/key\.location()/key.identifier()/g' "${HELPER_FILE}"
if grep -q 'key\.location()' "${HELPER_FILE}"; then
  echo "[NeverFolia] Failed to normalize ResourceKey API in placement helper" >&2
  exit 3
fi

echo "[NeverFolia] Applying NeverOverworld native Jigsaw placement resolver"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-placement-hook.py" "${FOLIA_DIR}"
echo "[NeverFolia] Normalizing NeverOverworld ChunkPos API for Minecraft 26.2"
python3 "${ROOT_DIR}/scripts/normalize-never-overworld-placement-chunkpos-api.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld predictive no-generation fast locate"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-fast-locate.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld flooded vanilla predictive fast locate"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-vanilla-fast-locate.py" "${FOLIA_DIR}"
echo "[NeverFolia] Scoping flooded vanilla predictive locate to NeverOverworld only"
python3 "${ROOT_DIR}/scripts/harden-never-overworld-vanilla-fast-locate-scope.py" "${FOLIA_DIR}"
echo "[NeverFolia] Replacing vanilla fast-locate vertical surface scans with preliminary density sampling"
python3 "${ROOT_DIR}/scripts/optimize-never-overworld-vanilla-fast-locate.py" "${FOLIA_DIR}"

echo "[NeverFolia] Rejecting submerged vanilla dry-land structure starts"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-flooded-surface-structure-policy.py" "${FOLIA_DIR}"

echo "[NeverFolia] Forcing vanilla mineshafts into the NeverOverworld deep range"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-mineshaft-depth-policy.py" "${FOLIA_DIR}"

echo "[NeverFolia] Re-anchoring swamp huts to the flooded waterline"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-swamp-hut-waterline.py" "${FOLIA_DIR}"

echo "[NeverFolia] Accepting XYZ syntax in the Folia region profiler"
python3 "${ROOT_DIR}/scripts/apply-neverfolia-profiler-xyz.py" "${FOLIA_DIR}"

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

echo "[NeverFolia] Applying NeverOverworld sculk worldgen chunk ownership hook"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-sculk-ownership.py" "${FOLIA_DIR}"

# The datapack resolves original vanilla 26.2 above_bottom/below_top anchors to
# absolute coordinates. OreFeature also needs its old build-bound rejection,
# otherwise anchors that intentionally sample outside -64..319 (notably diamond,
# redstone, emerald and upper iron) become writable in the extended NR dimension.
echo "[NeverFolia] Preserving original vanilla 26.2 resource-ore write bounds"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-vanilla-ore-write-bounds.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld native deterministic ore geology"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-ore-geology.py" "${FOLIA_DIR}"

echo "[NeverFolia] Extending NeverOverworld native ore geology with coal and emerald"
python3 "${ROOT_DIR}/scripts/extend-never-overworld-ore-geology.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying established deep diamond and emerald balance v2"
python3 "${ROOT_DIR}/scripts/tune-never-overworld-ore-balance.py" "${FOLIA_DIR}"

echo "[NeverFolia] Calibrating all NeverOverworld deep ores toward measured vanilla 26.2 density"
python3 "${ROOT_DIR}/scripts/tune-never-overworld-ore-balance-v3.py" "${FOLIA_DIR}"

echo "[NeverFolia] Relocating NeverOverworld native geology to SURFACE before CARVERS"
python3 "${ROOT_DIR}/scripts/relocate-never-overworld-ore-geology-surface.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld Moonrise LIGHT flood barrier"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-moonrise-light-flood-hook.py" "${FOLIA_DIR}"

echo "[NeverFolia] Applying NeverOverworld deterministic floodable-volume semantics"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-floodable-volume.py" "${FOLIA_DIR}"

echo "[NeverFolia] Removing flooded tree remnants, old shoreline flora and exposed rails"
python3 "${ROOT_DIR}/scripts/harden-never-overworld-flood-ecology.py" "${FOLIA_DIR}"

echo "[NeverFolia] Relocating sugar cane and lily pads to the new Y=128 shoreline"
python3 "${ROOT_DIR}/scripts/adapt-never-overworld-flood-shoreline-flora.py" "${FOLIA_DIR}"

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
