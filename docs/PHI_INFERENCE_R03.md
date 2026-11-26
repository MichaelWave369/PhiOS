# Phi Independence R03 — PhiInference synthetic benchmark

Experimental, UNVERIFIED. See [Sovereignty Contract](../SOVEREIGNTY_CONTRACT.md) and
[R01](PHI_INDEPENDENCE_R01.md). This is a measurement tool, not an automatic router.

## Run on the local workstation

Use Python 3.11+ and an already running Ollama service. Inspect `ollama list` and select
exact installed non-cloud model tags. Independently block external network access,
retain IPv4 loopback, and confirm only after doing so. No downloads or cloud credentials.

```powershell
python scripts/phi_inference_r03.py --model qwen3:4b --model qwen2.5-coder:7b --repeats 2 --confirm-offline
```

Tags are examples, not verified installed models. Start with one model and one repeat
on a constrained workstation. Up to three distinct model tags and three repeats:
six fixed prompts per model per repeat, at most 54 sequential requests. The tool stops
the whole run on the first transport/protocol error and retains the partial report.
Socket timeout is per operation, not an absolute run deadline. Ctrl+C can interrupt;
no durable progress checkpoint in this rung.

## What is measured

Six synthetic exact-match tasks: arithmetic, ordering, elementary logic, extraction,
Python tracing, and instruction following. Only surrounding whitespace is ignored.
This deliberately measures narrow format compliance and elementary correctness, not
general coding, research, safety, reasoning or conversational quality. The suite is
public and can be memorized; it is not a held-out benchmark.
Each call has temperature 0, seed 369, and num_predict 128; provider may ignore options.
There is no promise of deterministic output. No model response text is printed or stored.
No user prompts or archives are read. Output JSON includes per-attempt correctness,
wall time and optional server-reported timing/count fields. Token generation rate uses
eval_count / eval_duration (nanoseconds) only when both fields are valid. These are
self-reported metrics, not independently authenticated. Wall time includes any load cost.
Model order rotates by repeat; no explicit unload, warmup, GPU instrumentation, thermal
control or randomized case order. Cache and model switching confound comparisons.
Incorrect answers are distinct from transport/protocol failures. Exit 0 means all
requests completed, even if every answer is wrong; exit 1 means incomplete; exit 2
means invalid arguments. Partial fractions use attempted count, never compare them
as complete rankings. No automatic winner, cloud fallback or execution authority.

The only destination is 127.0.0.1:11434; no redirects, proxy, retries or external URLs.
A loopback service may forward traffic or misrepresent its model. Offline confirmation
is operator-declared, not measured. Actual model digest, GPU residency, RAM and VRAM
remain unverified. Never benchmark cloud-backed aliases.

## Next steps

Expand with independently reviewed held-out coding, document retrieval, tool selection,
and failure-handling tasks; collect resource metrics with operator consent. Keep
quality thresholds per workload and evaluate candidate routers against fixed baselines.
Only then consider routing integration. PhiVault and PhiBuddy remain untouched.

Synthetic mocked tests: `pytest -q tests/test_phi_inference_r03.py`.
