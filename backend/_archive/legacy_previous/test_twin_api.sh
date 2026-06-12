cat > test_twin_api.sh <<'SH'
#!/usr/bin/env bash
set -e

BASE="http://127.0.0.1:8000"
DATE1="${1:-2023-12-29}"
DATE2="${2:-2023-12-30}"

echo "== 1. dates =="
curl -s "$BASE/api/tbm/dates" | python -m json.tool | head -n 40

echo
echo "== 2. trigger summary for $DATE2 =="
curl -s "$BASE/api/tbm/summary?date=$DATE2" | python -m json.tool | head -n 60

echo
echo "== 3. twin state =="
curl -s "$BASE/api/tbm/digital_twin_state?date=$DATE2" | python -m json.tool | head -n 120

echo
echo "== 4. twin events =="
curl -s "$BASE/api/tbm/twin/events?date=$DATE2" | python -m json.tool | head -n 120

echo
echo "== 5. twin diff =="
curl -s "$BASE/api/tbm/twin/diff?date1=$DATE1&date2=$DATE2" | python -m json.tool | head -n 120

echo
echo "Done."
SH

chmod +x test_twin_api.sh