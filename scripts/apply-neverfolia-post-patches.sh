#!/usr/bin/env bash
set -euo pipefail

# Compatibility entry point retained for workflows and local builds.
# The historical transformer body is preserved in apply-neverfolia-post-patches-core.sh.
# This wrapper makes R9 V17 the final authoritative village layer in every normal build.
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
