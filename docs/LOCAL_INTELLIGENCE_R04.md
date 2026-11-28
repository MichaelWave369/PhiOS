# Operation Local Intelligence R0.4 — Local Builder

A common proposal-only engineering exercise for local collaborators. The first
pilot measures three small integer-predicate repairs, not autonomous software
engineering. The candidate is data, not an executable patch.

## Run the pilot

From PhiOS on Python 3.11+:

```powershell
python -m phios.local_builder_review suite
python -m phios.local_builder_review review --candidate candidate.json
python -m pytest tests/test_local_builder_review.py
```

Copy the public suite into an already qualified local companion and request
the JSON response. Use an isolated session, a reviewed local checkpoint and
offline operation. Manually save the response as UTF-8 JSON in a disposable
directory. Do not run code, enable tools, mount a production workspace or
provide credentials. Remove Markdown fences only if necessary, recording any
manual transformation; do not repair the candidate before scoring.

The envelope is:

```json
{"schema":"phios.local-builder.candidate.r04","repairs":[{"id":"port_bounds","expression":"YOUR_EXPRESSION"},{"id":"byte_budget","expression":"YOUR_EXPRESSION"},{"id":"retry_limit","expression":"YOUR_EXPRESSION"}]}
```

The reviewer parses a narrowly allowlisted Python-expression grammar, then
interprets its own integer/Boolean operations on 263 predetermined inputs
(11 port, 216 budget, 36 retry). No eval, exec, compile, import, subprocess,
network calls, repository edits or application launch. Candidate input is
bounded to 64 KiB, each expression to 256 characters and 40 AST nodes.
Only comparisons, integer arithmetic, strict Boolean operators and parameter
names are supported. This is not a general Python interpreter: Boolean
operands are checked eagerly, and unsupported constructs are refused.
The receipt contains a candidate hash and per-task fixture counts, not source
text or filesystem paths. Exit 0 means all fixtures match; exit 3 means
at least one fixture mismatch; exit 2 means invalid or unreadable input.

## Native companion pathways (manual, no new grants)

- BrainC: disposable native chat with tools_enabled=false, as in R0.3c.
- PhiBuddy: isolated Solo or Council chat; use a fresh --db or disposable
  session as appropriate, and review raw answers privately.
- Agentora: isolated local instance; default mock mode is not inference.
  Explicitly verify the real local model configuration, disable worker
  dispatch, software mission integrations, writeback and optional
  action capabilities. Use only a proposal-only chat/review flow; never
  approve an action for this exercise. No automatic Agentora adapter.
- PhiBot: use advisory-only, source-pinned review where appropriate.
  Its PHIBOT-38 crew review is Markdown-oriented; this JSON exercise
  does not match that native interface automatically. Do not use its
  write, commit, remote steward or Reality Gate grant paths in R0.4.

Reviewed source entrypoints: Agentora README at
13b6ad71e57771ae38c6cf8d519ce55a43d51440 and PhiBot README at
c394ca3a90eba9081da1428208f115e76f1bc3a1. Review later changes and
native setup guides before enabling any live workflow.

## Evidence and next gates

Finite public fixtures are not proof of general correctness or intelligence;
answers may overfit the fixture domain or be written by a human. The
candidate origin, model identity, offline inference and native application
execution are not authenticated. Do not compare model families or Council
quality based on a single run; record hardware, model, timing, repeat
conditions and independent human review separately.

Next: collect actual operator-machine receipts; introduce a disposable
source-file patch exercise with a separately reviewed, isolated test
runner; only then consider an explicit human-approved apply path using
existing native governance. No new authorization is granted here.
