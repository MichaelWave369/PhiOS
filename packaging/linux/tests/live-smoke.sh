#!/usr/bin/env bash
# This fixture is included only when PHIOS_CI_SMOKE=1; it performs no disk writes.
set -euo pipefail
dump_failure() {
    journalctl -b -u greetd --no-pager
    runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 journalctl --user -b --no-pager || true
    cat /home/phios/.local/state/phios/wayfire.log || true
    echo PHIOS_BOOT_FAILED
}
trap dump_failure ERR
for attempt in {1..420}; do
    if curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null &&
       pgrep -u phios -x wayfire >/dev/null && pgrep -u phios -x chromium >/dev/null; then
        break
    fi
    if (( attempt % 60 == 0 )); then
        journalctl -b -u greetd --no-pager
        cat /home/phios/.local/state/phios/wayfire.log || true
    fi
    sleep 1
done
curl -fsS http://127.0.0.1:3969/ | grep -q '<div id="root">'
curl -fsS http://127.0.0.1:3969/api/v1/package-observation | python -c 'import json,sys; p=json.load(sys.stdin)["observation"]; assert p["adapter"]=="arch-pacman-local" and p["availability"]=="available" and not p["executionAuthority"] and not p["effectPerformed"]'
curl -fsS http://127.0.0.1:3969/api/v1/system-state | python -c 'import json,sys; r=json.load(sys.stdin)["receipt"]; p=next(c for c in r["components"] if c["id"]=="packages"); assert p["source"]=="pacman-local-desc" and p["availability"]=="available" and r["readOnly"] and not r["executionAuthority"] and not r["effectPerformed"]'
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
userctl() { runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user "$@"; }
old_pid=$(userctl show phios-observer.service --property=MainPID --value)
userctl kill --signal=KILL phios-observer.service
for attempt in {1..60}; do
    new_pid=$(userctl show phios-observer.service --property=MainPID --value)
    if [[ $new_pid != 0 && $new_pid != "$old_pid" ]] && curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null; then
        break
    fi
    sleep 1
done
test "$new_pid" != "$old_pid"
curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null
# A compositor exit must stop every PartOf session service. Restarting greetd
# opens a fresh configured live login; no terminal workaround launches the UI.
pkill -TERM -u phios -x wayfire
for attempt in {1..30}; do
    if ! userctl is-active --quiet phios-session.target; then break; fi
    sleep 1
done
! userctl is-active --quiet phios-session.target
! curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null
systemctl restart greetd
for attempt in {1..90}; do
    if curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null &&
       pgrep -u phios -x wayfire >/dev/null && pgrep -u phios -x chromium >/dev/null; then break; fi
    sleep 1
done
userctl is-active phios-observer.service phios-browser.service phios-curiosity-reader.service
curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null
echo PHIOS_SESSION_RESTART_OK
python -c 'import phios, phios.mcp.server, phios.ghostwalk_operator; print("Installed Python runtime:",phios.__version__)'
phi version
printf 'PHIOS_BOOT_OK:%s:%s\n' "$(cat /usr/share/phios/source-commit)" "$(tr -d '-' < /proc/sys/kernel/random/boot_id)"
