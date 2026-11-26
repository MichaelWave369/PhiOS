# Phi Independence R06-B — single-job remote synthetic inference

Experimental. Reuses R06-A TLS trust and peer fencing, R03 fixed benchmark cases.
One operator-approved job per persistent SQLite journal, no arbitrary prompt,
automatic scheduling, shell, source changes, private conversation data or cloud
fallback. Separate port TCP 3770. Do not expose Ollama itself to the LAN.

## Pilot

Use R06-A private LAN, certificate, pin, token and firewall procedure (restrict
TCP 3770 instead of 3769). Independently deny WAN on both PCs while retaining LAN
and loopback. Install the selected non-cloud model on the secondary beforehand.
Use a new random 64-hex job ID (e.g. Python secrets.token_hex(32)), share it with
both operators. In PowerShell on each machine set the same task arguments:

```powershell
$taskArgs = @('--job','YOUR_64_HEX_JOB','--node','node02','--model','qwen3:4b','--case','logic')
python -m scripts.phi_mesh_r06b plan @taskArgs
```

Review the task digest. On each host set $approval to the exact reviewed digest.
All following commands use --confirm-offline-lan only after external network
blocking and peer verification. Secondary: use a private ACL-restricted directory
outside Git on reliable local storage. Start Ollama on localhost first.

```powershell
python -m scripts.phi_mesh_r06b init @taskArgs --db D:/PhiMesh/job.sqlite --approve-digest $approval --confirm-offline-lan
python -m scripts.phi_mesh_r06b serve @taskArgs --db D:/PhiMesh/job.sqlite --ip 192.168.1.20 --peer 192.168.1.10 --cert D:/PhiMesh/cert.pem --key D:/PhiMesh/key.pem --token-file D:/PhiMesh/token.txt --approve-digest $approval --confirm-offline-lan
```

Primary (replace IP, model, paths and pin with actual trusted values):

```powershell
python -m scripts.phi_mesh_r06b submit @taskArgs --ip 192.168.1.20 --cert D:/PhiMesh/cert.pem --pin YOUR_CERT_PIN --token-file D:/PhiMesh/token.txt --approve-digest $approval --confirm-offline-lan
```

If disconnected or uncertain, restart **serve** with the same intact journal and
task; query by replacing submit with status. Status never invokes inference.
Do not initialize again or restore an older journal to repeat an uncertain job.
The journal must remain private; losing, deleting, rolling back or cloning it
invalidates the duplicate-admission guarantee. New jobs require a new ID, new
journal and explicit approval on both machines.

## States

NOT_ADMITTED: no recorded admission. OUTCOME_UNKNOWN: committed admission
before inference, but no durable terminal result; do not automatically retry.
FINISHED: R03 returned CORRECT, INCORRECT or ERROR. A completed transport error
is not a successful inference. Even CORRECT is only a peer-reported synthetic
exact match, not attestation of model or hardware identity.

SQLite transaction with synchronous FULL commits admission before the model
call. Reopening the same intact journal or submitting the same task again does
not issue a second call. This is at-most-once admission, not exactly-once
execution or proof that the daemon didn't internally retry. Power-loss guarantees
depend on filesystem/storage behavior. No automatic retry, reset, migration or
repair. A crash before the terminal commit leaves OUTCOME_UNKNOWN indefinitely.

The trusted private LAN listener is single-threaded, accepts at most three
handle_request iterations per launch, and uses socket operation timeouts, not
hard wall-clock deadlines. No service install, public fallback or remote worker
authority. The bearer is sent only after verified TLS IP and live certificate pin.
The exact operator-approved task digest binds job/node/model/case but is not a
signature or proof of human identity. The daemon is trusted to be local; physical
offline status not independently measured. The client cannot attest the peer
actually ran the model. No claim of EXIT-VERIFIED.

Tests: pytest -q tests/test_phi_mesh_r06b.py (real SQLite, mocked inference and
CLI dispatch). R06-A separately tests ephemeral TLS; R06-B live endpoint and
two-PC inference remain to be field tested.
