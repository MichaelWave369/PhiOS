# Operation Local Intelligence R0.3 — First Contact

A bounded, operator-initiated two-turn Ollama API smoke test, separate from
the companion applications. R0.1 catalogs capabilities; R0.2 and R0.2b
inspect selected checkpoint and manifest bytes. None is an inference proof.

## Windows field pilot

Use a trusted Ollama service already running on the operator machine.
First use the R0.2b manifest review on the intended model, then disconnect
external networking if testing offline operation. Ensure the chosen tag
actually corresponds to the reviewed manifest. This tool does not perform
that binding automatically.

```powershell
python -m phios.local_intelligence --ollama
python -m phios.local_chat_smoke --model qwen3:4b
python -m phios.local_chat_smoke --model qwen3:4b --run-live
python -m pytest tests/test_local_chat_smoke.py
```

Replace qwen3:4b with an exact installed tag. The command without --run-live
performs no network requests. With explicit opt-in, it GETs /api/tags and
requires a single exact matching entry without recognized cloud markers.
It sends at most two POST /api/chat requests to fixed 127.0.0.1:11434.
No proxy, redirects, tools, downloads, shell commands, private prompts,
or filesystem writes are requested. No automatic retry or fallback.

The fixed public prompt asks for READY while providing a test code, then
asks for that code in a second request that includes the prior conversation.
Only the expected acknowledgment is replayed. The output checks are exact
after trimming whitespace; a reasoning model that exhausts its token budget
or emits extra prose can fail without being broken. Requests specify 96
predicted tokens, 2048 context and temperature zero; backend adherence is
not independently enforced. --timeout sets the socket operation timeout
(1–120 seconds, default 60), not a total wall-clock deadline. Responses
are bounded to 2 MiB each.

## Receipt and evidence boundary

- LOOPBACK_CHAT_MATCH_REVIEW_ONLY (exit 0): both responses match.
- RESPONSE_MISMATCH (exit 3): an exact response check failed.
- BACKEND_OR_RESPONSE_UNQUALIFIED (exit 2): missing model, cloud hint,
  transport failure, incomplete response or invalid input.
- NOT_RUN_EXPLICIT_OPT_IN_REQUIRED (exit 2): no calls.

Receipts omit model names, prompts and generated text; measured wall
seconds and optional backend-declared token/duration metrics remain.
Timing can differ for warm and cold loads. The reported tokens/sec uses
backend counters, not independent tokenization or GPU telemetry.

Loopback does not prove the service is genuine, that inference happened,
or that remote forwarding is impossible. Fixed prompts and a mock can
produce the expected answer. CI fixtures explicitly use mocked responses.
The test checks observable protocol behavior only; it does not certify
offline execution, model intelligence, durable memory, security or any
individual companion integration. A trusted service, actual field
observations and independently checked networking/hardware are required.
A live call can load a model into RAM/VRAM and affect other workloads.

## Next steps

Qualify BrainC and PhiBuddy independently using the same verified model
and an operator-observed offline run. Then qualify GAIA, Vessie,
PocketBrain, PrivateSpark, ThinkTank and Agentora through their actual
local entrypoints; distinguish simulation/mock modes from live inference.
Do not give any tool or workspace write authority during chat tests.
