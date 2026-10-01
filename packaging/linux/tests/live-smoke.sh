#!/usr/bin/env bash
# CI-only. Disk writes require the install fixture's exact disposable disk.
set -euo pipefail
dump_failure() {
    echo PHIOS_BOOT_FAILED
    timeout 15 journalctl -b -u greetd --no-pager || true
    timeout 15 runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 journalctl --user -b --no-pager || true
    cat /home/phios/.local/state/phios/wayfire.log || true
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
if id -nG phios | grep -qw wheel; then false; fi
if pgrep -u root -x wayfire; then false; fi
if pgrep -u root -x chromium; then false; fi
for pid in $(pgrep -u phios -x chromium); do
    if tr '\0' '\n' < "/proc/$pid/cmdline" | grep -qx -- '--no-sandbox'; then false; fi
done
for endpoint in decisions bindings leases; do
    status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' --data '{}' "http://127.0.0.1:3969/api/v1/ghostwalk/authorization-console/$endpoint")
    test "$status" = 403
done
runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active phios-observer.service phios-browser.service phios-curiosity-reader.service
userctl() { runuser -u phios -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user "$@"; }
old_pid=$(userctl show phios-observer.service --property=MainPID --value)
[[ $old_pid =~ ^[1-9][0-9]*$ ]]
userctl kill --signal=KILL phios-observer.service
for attempt in {1..60}; do
    new_pid=$(userctl show phios-observer.service --property=MainPID --value)
    if [[ $new_pid != 0 && $new_pid != "$old_pid" ]] && curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null; then
        break
    fi
    sleep 1
done
test "$new_pid" != "$old_pid"
[[ $new_pid =~ ^[1-9][0-9]*$ ]]
curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null
echo PHIOS_SIDECAR_RESTART_OK
# A compositor exit must stop every PartOf session service. Restarting greetd
# does not repeat initial_session. The VM driver enters the public volatile
# live credentials at the real greeter; production login policy stays intact.
pkill -TERM -u phios -x wayfire
for attempt in {1..30}; do
    if ! userctl is-active --quiet phios-session.target &&
       ! curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null; then break; fi
    sleep 1
done
if userctl is-active --quiet phios-session.target; then false; fi
if curl -fsS http://127.0.0.1:3969/api/v1/health >/dev/null; then false; fi
printf 'PHIOS_LOGIN_REQUIRED:%s\n' "$(tr -d '-' < /proc/sys/kernel/random/boot_id)"
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
if [[ -b /dev/vda ]]; then
    python /usr/local/bin/phios-live-install-smoke.py
fi
