#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/Folia" >&2
  exit 2
fi

FOLIA_DIR="$(realpath "$1")"
LOG_FILE="${FOLIA_DIR}/.neverfolia-apply-patches.log"

run_apply() {
  (
    cd "${FOLIA_DIR}"
    ./gradlew applyAllPatches --stacktrace
  ) 2>&1 | tee "${LOG_FILE}"
}

if run_apply; then
  exit 0
fi

# paperweight occasionally fails while copying its temporary git worktree because
# a loose object directory disappears during SetupForkMinecraftSources. This is
# infrastructure/cache corruption, not a source patch conflict. Retry exactly once
# only for that narrow signature; every other failure remains a hard CI failure.
if ! grep -Fq 'java.nio.file.NoSuchFileException:' "${LOG_FILE}" \
  || ! grep -Fq '/paperweight/upstreams/server-work/' "${LOG_FILE}" \
  || ! grep -Fq '/.git/objects/' "${LOG_FILE}"; then
  echo '[NeverFolia CI] applyAllPatches failed for a non-retryable reason.' >&2
  exit 1
fi

echo '[NeverFolia CI] transient paperweight worktree corruption detected; cleaning server-work and retrying once.' >&2
rm -rf "${FOLIA_DIR}/.gradle/caches/paperweight/upstreams/server-work"
rm -f "${LOG_FILE}"

if run_apply; then
  echo '[NeverFolia CI] applyAllPatches retry succeeded.'
  exit 0
fi

echo '[NeverFolia CI] applyAllPatches retry failed.' >&2
exit 1
