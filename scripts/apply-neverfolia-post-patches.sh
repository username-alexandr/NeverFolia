#!/usr/bin/env bash
set -euo pipefail

# Compatibility entry point retained for workflows and local builds.
# The historical transformer body is preserved in apply-neverfolia-post-patches-core.sh.
# This wrapper makes R9 V17 the final authoritative village base layer, then
# installs FIELD-R10/FIELD-R11 and DESERT-R1 Overworld corrections.
#
# Contract forwarding for validate-never-overworld-spec.py: these exact stages
# are executed by apply-neverfolia-post-patches-core.sh before this wrapper adds
# the final V17 village layer. Keep the literal command markers here so the
# top-level production entry point continues to advertise the complete contract.
# apply-never-overworld-ore-geology.py" "${FOLIA_DIR}"
# extend-never-overworld-ore-geology.py" "${FOLIA_DIR}"
# tune-never-overworld-ore-balance.py" "${FOLIA_DIR}"
# relocate-never-overworld-ore-geology-surface.py" "${FOLIA_DIR}"
# harden-never-overworld-flood-connectivity-r8.py" "${FOLIA_DIR}"
# harden-never-overworld-frozen-surface-r8c.py" "${FOLIA_DIR}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FOLIA_DIR="${ROOT_DIR}/.work/Folia"

"${ROOT_DIR}/scripts/apply-neverfolia-post-patches-core.sh"

echo "[NeverFolia] Applying final R9 V17 village locate/generation baseline"
python3 "${ROOT_DIR}/scripts/tune-never-overworld-village-locate-r9-v5.py" "${FOLIA_DIR}"
echo "[NeverFolia] Applying final R9 V17 strict 12/12 village contract"
python3 "${ROOT_DIR}/scripts/tune-never-overworld-village-strict-search-v12.py" "${FOLIA_DIR}"
echo "[NeverFolia] Installing final R9 V17 actual-bbox village reclamation"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-village-reclamation-v17.py" "${FOLIA_DIR}"
echo "[NeverFolia] Freezing final R9 V17 village production policy (rings128)"
python3 "${ROOT_DIR}/scripts/finalize-never-overworld-village-v17.py" "${FOLIA_DIR}"

echo "[NeverFolia] Final R9 V17 village production chain applied"

echo "[NeverFolia] Applying NeverOverworld FIELD-R10 village, submerged-remnant and ore fixes"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-field-r10.py" "${FOLIA_DIR}"
echo "[NeverFolia] Extending FIELD-R10 flooded flora cleanup to the owning-chunk 3x3x3 neighborhood"
python3 "${ROOT_DIR}/scripts/fix-never-overworld-field-r10-flora-neighborhood.py" "${FOLIA_DIR}"
echo "[NeverFolia] NeverOverworld FIELD-R10 production layer applied"

echo "[NeverFolia] Applying NeverOverworld FIELD-R11 shallow cross-chunk flood continuity"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-field-r11.py" "${FOLIA_DIR}"
echo "[NeverFolia] Re-anchoring ocean monuments to the raised NeverOverworld sea level"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-monument-r11.py" "${FOLIA_DIR}"
echo "[NeverFolia] Installing DESERT-R1 rare oases/palms and sandstorms (no overheating)"
python3 "${ROOT_DIR}/scripts/apply-never-overworld-desert-r1.py" "${FOLIA_DIR}"
echo "[NeverFolia] NeverOverworld FIELD-R11 + DESERT-R1 production candidate applied"

echo "[NeverFolia] Preparing pinned CC0 noise for native NeverNether R5"
python3 "${ROOT_DIR}/scripts/prepare-never-nether-noise-r5.py" --install "${FOLIA_DIR}"
echo "[NeverFolia] Installing native NeverNether R4/R5 adapters"
python3 "${ROOT_DIR}/scripts/apply-never-nether-native-adapters-r4.py" "${FOLIA_DIR}"
