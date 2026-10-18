#!/usr/bin/env bash
# Fail if the working tree still contains strings that must not be public.
# Scans tracked and untracked files, skips .git. Fixture emails on
# example.invalid and the documented fake bearer in the execution-control
# negtest are allowed.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
report() {
  printf 'HYGIENE %s\n' "$1"
  fail=1
}

# High-confidence secret and identity patterns. The negtest bearer
# "sk-supersecretvalue" is shorter than the sk- threshold on purpose.
# Patterns are hex so this file does not embed the literals it rejects.
_hx() { printf '%b' "$(printf '%s' "$1" | sed 's/../\\x&/g')"; }
patterns=()
patterns+=("$(_hx 2f55736572732f5b412d5a612d7a302d392e5f2d5d2b)")
patterns+=("$(_hx 2f686f6d652f5b412d5a612d7a302d392e5f2d5d2b)")
patterns+=("$(_hx 6b6c6f6e67)")
patterns+=("$(_hx 4b656c76696e7c6b656c76696e)")
patterns+=("$(_hx 7761726d66616e7c7761726d2d66616e)")
patterns+=("$(_hx 737a3032)")
patterns+=("$(_hx 6d6163626f6f6b)")
patterns+=("$(_hx 7368656e6e6f6e67)")
patterns+=("$(_hx 6c6f6e676b6169)")
patterns+=("$(_hx 4071715c2e636f6d)")
patterns+=("$(_hx 40676d61696c5c2e636f6d)")
patterns+=("$(_hx 41497a615b302d39412d5a612d7a5f2d5d7b31302c7d)")
patterns+=("$(_hx 414b49415b302d39412d5a5d7b31367d)")
patterns+=("$(_hx 6768705f5b412d5a612d7a302d395d7b32302c7d7c67686f5f5b412d5a612d7a302d395d7b32302c7d7c6769746875625f7061745f5b412d5a612d7a302d395f5d7b32302c7d)")
patterns+=("$(_hx 786f785b62617072735d2d5b412d5a612d7a302d392d5d7b31302c7d)")
patterns+=("$(_hx 7368702861747c73737c63617c7061295f)")
patterns+=("$(_hx 736b2d5b412d5a612d7a302d395d7b32302c7d)")
patterns+=("$(_hx 2d2d2d2d2d424547494e205b412d5a205d2a50524956415445204b45592d2d2d2d2d)")
patterns+=("$(_hx 5c623130305c2e28365b342d395d7c5b372d395d5b302d395d7c315b302d315d5b302d395d7c31325b302d375d295c2e5b302d395d7b312c337d5c2e5b302d395d7b312c337d5c62)")
patterns+=("$(_hx 5c6231305c2e5b302d395d7b312c337d5c2e5b302d395d7b312c337d5c2e5b302d395d7b312c337d5c62)")
patterns+=("$(_hx 5c623139325c2e3136385c2e5b302d395d7b312c337d5c2e5b302d395d7b312c337d5c62)")
patterns+=("$(_hx 5c623137325c2e28315b362d395d7c325b302d395d7c335b302d315d295c2e5b302d395d7b312c337d5c2e5b302d395d7b312c337d5c62)")
patterns+=("$(_hx 7465616d5f69647c7465616d49647c6f72675f69647c6f7267616e697a6174696f6e5f6964)")
patterns+=("$(_hx 636f6d5c2e6b6c6f6e67)")
patterns+=("$(_hx 3131333633303233)")

while IFS= read -r -d '' file; do
  for pat in "${patterns[@]}"; do
    if grep -E -n -I -H "$pat" "$file" >/tmp/hygiene-hit.txt 2>/dev/null; then
      # example.invalid addresses are fixtures, not mailboxes.
      if [[ "$pat" == *@* ]]; then
        if grep -E -v 'example\.invalid' /tmp/hygiene-hit.txt | grep -q .; then
          grep -E -v 'example\.invalid' /tmp/hygiene-hit.txt
          report "pattern /$pat/ in $file"
        fi
      else
        cat /tmp/hygiene-hit.txt
        report "pattern /$pat/ in $file"
      fi
    fi
  done
done < <(find . -type f \
  -not -path './.git/*' \
  -not -path './scripts/public-hygiene.sh' \
  -print0)

if [[ "$fail" -ne 0 ]]; then
  echo "public hygiene: FAIL"
  exit 1
fi
echo "public hygiene: PASS"
exit 0
