#!/bin/bash
# Quarterly data refresh: scrape new minutes, refresh DataSF, rebuild release.
#
#   ./update.sh            regular update (skips the slow Wayback staff panel)
#   ./update.sh --full     also refresh the Wayback staff panel (~30 min)
#
# Downloads are incremental: already-cached minutes are skipped, so a
# quarterly run only fetches the new hearings plus fresh DataSF extracts.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python

if [ ! -x "$PY" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "== 1/8 scrape minutes (incremental)"
$PY pipeline/scrape.py
echo "== 2/8 retry any failed downloads"
$PY pipeline/retry_failed.py
echo "== 3/8 fetch DataSF projects + geocoding data"
$PY pipeline/fetch_datasf.py
if [ "${1:-}" = "--full" ]; then
  echo "== 3b   refresh Wayback staff panel"
  $PY pipeline/wayback_staff.py
fi
echo "== 4/8 parse minutes -> items"
$PY pipeline/build_items.py
echo "== 5/8 extract speakers -> comments"
$PY pipeline/build_comments.py
$PY pipeline/clean_names.py
echo "== 6/8 outcome coding + DataSF join + geocoding"
$PY pipeline/build_projects.py
echo "== 7/8 roles + polarity imputation"
$PY pipeline/assign_roles.py
$PY pipeline/impute_polarity.py
echo "== 8/8 assemble public/"
$PY pipeline/finalize.py
echo "Done. Review data/validation/ before committing public/."
