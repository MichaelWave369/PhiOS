# Operation Local Intelligence R0.3c — BrainC native chat pilot

This is an operator-driven field test of BrainC's actual authenticated chat
and history routes. It does not launch BrainC or Ollama, install dependencies,
register accounts, change preferences, delete history, or modify existing
applications. It intentionally writes test chat messages to the disposable
BrainC instance only after explicit opt-in.

## Prepare a disposable Windows instance

Review BrainC source at b77a73ed3b431b3fdd783e774ddb0e0aa6fca06e and any changes
since then. Use a separate checkout and a fresh empty memory directory;
do not copy an existing database, backup, workspace or .env. Prepare the
Python environment, cached embedding assets and installed Ollama model
before disconnecting external networking. Use a fresh local secret and
disposable account. Do not reuse a personal account or token. Start BrainC
using its documented dependencies and configuration, but bind Uvicorn
to the dedicated pilot address, not the normal startup script's LAN bind:

```powershell
$env:BRAINC_INFERENCE_BACKEND = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:ACTIVE_MODEL = "qwen3:4b"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8369
```

Set the disposable account's model preference to the same exact installed
tag through BrainC before testing. Verify the actual service and model,
empty store, offline networking and cached embeddings yourself. Stop if
isolation or dependency readiness is uncertain. The native chat route
performs semantic recall and stores embeddings even with tools disabled.
The readiness route's zero message count is only a server claim, not proof
of filesystem isolation. No other clients should use the instance.

## Execute from PhiOS

```powershell
python -m phios.local_brainc_smoke --model qwen3:4b --run-live --confirm-disposable-offline
python -m pytest tests/test_local_brainc_smoke.py
```

The command prompts for the disposable access token with hidden input;
do not paste it into ChatGPT, Git, a shell command, or a shared log. Without
both switches no credential prompt or request is made. The CLI uses fixed
127.0.0.1:8369, an explicit route allowlist, bounded response bodies, and no
redirects or proxies. It checks readiness, zero messages, Ollama catalog,
account model preference and empty new conversation history before writing.
It submits two public First Contact prompts to native /chat with
tools_enabled=false, checks returned text, verifies ordered persisted
history after each turn, and checks the final reported message count.
Unexpected tool headers or incomplete/error responses stop the pilot.
No retry, rollback, or deletion is attempted. A failed run may have
persisted messages: start a fresh disposable instance for another attempt.

Receipts omit token, model name, conversation ID and message text. They
report exact-match checks, persisted-history agreement and elapsed wall
seconds. The response is collected through the native streaming HTTP
route; no independent time-to-first-token or token-rate measure is made.
Socket timeout is not a total wall-clock deadline.

Exit 0 means NATIVE_CHAT_MATCH_REVIEW_ONLY; 3 means RESPONSE_MISMATCH;
2 means not opted in or unqualified response/configuration. No output
proves authentic neural generation, exact checkpoint identity, actual
offline operation, GPU use, tool isolation or security. CI tests mock
the backend; actual operator-machine qualification remains required.
