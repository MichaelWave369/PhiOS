# Operation Local Intelligence R0.3b — Meet the Crew

Source-reviewed native application pilot. This rung creates a public PhiBuddy
case suite and an offline report reviewer; it does not launch either app.
Source references: PhiBuddy commit 5832141379174938bdd4d5487c698e228ccb9537
(Council Lab, CLI and evaluation source); BrainC commit
b77a73ed3b431b3fdd783e774ddb0e0aa6fca06e (chat route, inference, embeddings,
configuration and memory). Review any later changes before running.

## PhiBuddy native pilot (Windows)

Prepare the Rust toolchain and dependencies online, then disconnect external
networking for the field run. Select an actual installed local model after
R0.2b/First Contact review. These example commands use qwen3:4b; adapt as needed.
Use a private new directory for artifacts, and a new output filename on each run.

From PhiOS, with the output directory already created:

```powershell
python -m phios.local_companion_review suite | Set-Content -Encoding utf8NoBOM C:\\Pilot\\crew-cases.json
```

The command above requires PowerShell 7 for utf8NoBOM. On Windows PowerShell
5.1, use Python to write UTF-8 without a BOM instead (from PhiOS):

```powershell
python -c "from pathlib import Path; import json; from phios.local_companion_review import suite; Path(r'C:\\Pilot\\crew-cases.json').write_text(json.dumps(suite()), encoding='utf-8')"
```

From the PhiBuddy checkout:

```powershell
cargo run --offline -p phibuddy -- --model qwen3:4b --endpoint http://127.0.0.1:11434 eval --cases C:\\Pilot\\crew-cases.json --output C:\\Pilot\\crew-quick.jsonl --depth quick
```

The native eval workflow uses an in-memory database and refuses to overwrite
an existing output file. Full generated answers remain in the private JSONL.
From PhiOS:

```powershell
python -m phios.local_companion_review review --report C:\\Pilot\\crew-quick.jsonl --depth quick
```

The reviewer requires every case, exact prompt/reference, expected alternating
execution order and declared request counts. It returns a SHA-256 of the
input, declared elapsed times/call counts, exact checks on two literal-answer
tasks and a human-review requirement for the coding task. No generated text
or filenames appear in the review. Review a debate run separately with
--depth debate. Neither a valid report nor an exact answer proves live
inference or local-only execution; the report has no authenticated model ID.
Council uses more requests than Solo; this is not compute-matched, blinded,
or a general intelligence benchmark. Do not publish private raw reports.

## BrainC native chat: operator checklist, not automated

BrainC already has an explicit PhiServe transport and an Ollama default.
Its /chat route accepts tools_enabled (defaults true), uses semantic recall,
and persists chat and embeddings. A fresh conversation alone is not an
isolation boundary. Use a disposable checkout with a new empty memory store,
fresh credentials and no copied .env, backup or user data. Pre-cache the
embedding model and all dependencies, then disconnect external networking.
Bind the app to 127.0.0.1, not the startup script's 0.0.0.0; explicitly select
Ollama, its loopback URL and the intended model. Verify effective user model
preferences too. Do not change an existing installation or start downloads.
If dependencies are missing or isolation cannot be established, stop.

Use the native authenticated POST /chat endpoint with a new disposable
conversation ID and tools_enabled=false on every request. Submit the two
public First Contact messages in sequence, using the same conversation ID.
Check the actual streamed response and absence of X-Tool-Used, inspect the
stored conversation only in this disposable instance, and compare answers
to the expected acknowledgment and code. Do not expose tokens, private
logs or data. No automatic BrainC probe is implemented in this rung.

## Validation and next

Run python -m pytest tests/test_local_companion_review.py.
Fixture tests establish parser behavior only; no actual companion run is
claimed. Next: collect operator-observed native receipts, add an isolated
BrainC smoke harness, then qualify additional companion entrypoints.
