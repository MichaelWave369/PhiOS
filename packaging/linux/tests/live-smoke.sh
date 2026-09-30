#!/usr/bin/env bash
# This fixture is included only when PHIOS_CI_SMOKE=1; it performs no disk writes.
set -euo pipefail
trap 'journalctl -b -u greetd --no-pager; runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 journalctl --user -b --no-pager; echo PHIOS_BOOT_FAILED' ERR
for attempt in {1..420}; do
    if curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null &&
       pgrep -u phios -x wayfire >/dev/null && pgrep -u phios -x chromium >/dev/null; then
        break
    fi
    sleep 1
done
curl -fsS http://127.0.0.1:3969/ | grep -q '<div id="root">'
curl -fsS http://127.0.0.1:3969/api/v1/package-observation | python -c 'import json,sys; p=json.load(sys.stdin)["observation"]; assert p["adapter"]=="arch-pacman-local" and p["availability"]=="available" and not p["executionAuthority"] and not p["effectPerformed"]'
test "$(id -u phios)" = 1000
test "$(stat -c %a /home/phios/.local/state/phios)" = 700
! id -nG phios | grep -qw wheel
! pgrep -u root -x wayfire
! pgrep -u root -x chromium
for pid in $(pgrep -u phios -x chromium); do
    ! tr '\0' '\n' < "/proc/$pid/cmdline" | grep -qx -- '--no-sandbox'
done
for endpoint in decisions bindings leases; do
    status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' --data '{}' "http://127.0.0.1:3969/api/v1/ghostwalk/authorization-console/$endpoint")
    test "$status" = 403
done
runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active phios-observer.service phios-browser.service phios-curiosity-reader.service
python -c 'import phios, phios.mcp.server, phios.ghostwalk_operator; print("Installed Python runtime:",phios.__version__)'
phi version
printf 'PHIOS_BOOT_OK:%s\n' "$(cat /usr/share/phios/source-commit)"
