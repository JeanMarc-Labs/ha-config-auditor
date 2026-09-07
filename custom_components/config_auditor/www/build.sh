#!/usr/bin/env bash
# H.A.C.A Frontend Build Script
#
# Concatenates src/*.js in order and writes ONE bundle:
#   - haca-panel.<hash>.js       (the file the panel loads)
#   - haca-panel.hash            (that hash, for custom_panel.py and the tests)
#
# The hashed filename is the cache-bust mechanism. Browsers and (more
# importantly) the HA frontend service worker cannot serve a stale copy of
# a URL that never existed in their cache. Query-string cache-bust
# (`?v=<hash>`) was unreliable across some users because the SW could
# intercept and ignore the query string.
#
# Up to 1.8.0 an identical copy was also written as `haca-panel.js`, for
# back-compat with tooling that never materialised: 656 KB of dead weight in
# the repository and in every HACS download. Old `haca-panel.<oldhash>.js`
# files, and that canonical copy if it is still lying around, are cleaned up
# so the integration folder doesn't accumulate dead artefacts.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/src"

MODULES=(
  config_tab.js
  core.js
  pagination.js
  history.js
  complexity.js
  optimizer.js
  ai_explain.js
  dep_graph.js
  utils.js
  scan.js
  fixes.js
  reports.js
  issues.js
  battery.js
  battery_predict.js
  area_heatmap.js
  redundancy.js
  recorder_impact.js
  integrations.js
  closer.js
  compliance.js
  mcp_panel.js
)

TMP=$(mktemp)
for mod in "${MODULES[@]}"; do
  echo "// ── $mod ──────────────────────────────────────────" >> "$TMP"
  cat "$SRC/$mod" >> "$TMP"
  echo "" >> "$TMP"
done

# Compute content hash (first 8 chars of SHA256) for cache-busting. The name
# is the hash, so the bundle is written straight to its final path — this is
# the only file the build produces, and what custom_panel.py registers with HA.
HASH=$(sha256sum "$TMP" | cut -c1-8)
HASHED_OUT="$SCRIPT_DIR/haca-panel.$HASH.js"
HEADER="// HACA-BUILD: $HASH  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "$HEADER" | cat - "$TMP" > "$HASHED_OUT"
rm "$TMP"

# Clean up older hashed bundles (any haca-panel.XXXXXXXX.js whose hash is
# not the current one). Matches exactly 8 hex chars between the dots so we
# don't touch anything else.
for old in "$SCRIPT_DIR"/haca-panel.js "$SCRIPT_DIR"/haca-panel.*.js; do
  [ -e "$old" ] || continue
  base=$(basename "$old")
  # Match: haca-panel.js (the retired canonical copy), or haca-panel.<8 hex>.js
  # from an earlier build.
  is_stale_hashed=false
  if [[ "$base" =~ ^haca-panel\.[0-9a-f]{8}\.js$ ]] && [[ "$base" != "haca-panel.$HASH.js" ]]; then
    is_stale_hashed=true
  fi
  if [[ "$base" == "haca-panel.js" ]] || [[ "$is_stale_hashed" == true ]]; then
    rm -f "$old"
    echo "🧹 removed stale bundle: $base"
  fi
done

echo "$HASH" > "$SCRIPT_DIR/haca-panel.hash"
echo "✅ haca-panel.$HASH.js built — hash: $HASH  ($(wc -l < "$HASHED_OUT") lines)"
