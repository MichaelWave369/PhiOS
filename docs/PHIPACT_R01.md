# ΦPACT R0.1 — Proficiency, Accountability & Collaborative Trust

**Experimental, voluntary, offline, advisory only.** Capability is not authority.
This is a research scaffold for human–AI partnership assessment, not a human
certification scheme, model access control, or production permission boundary.

## Run

From the PhiOS source root (Python 3.11+):

~~~sh
python -m phios.phipact scenarios
python -m phios.phipact demo
python -m pytest -q tests/test_phipact_r01.py
~~~

The engine uses only the Python standard library and does not call models,
tools, networks, databases, or the authorization gateway. It does not persist
evidence, issue tokens, or collect identities.

## 3–6–9 research contract

Three distinct variables: human readiness, computational capability, operational
authority. Three evidence classes: E1 declared knowledge; E2 observed behavior
in controlled environments; E3 independent validation on unseen tasks.
R0.1 produces only **synthetic E2 proxies** from public answer-key fixtures,
not observations of actual human behavior.

Six scopes: general learning, advanced reasoning, reversible sandbox simulation,
infrastructure, delegated autonomy, frontier research. Ordinary learning is
not gated by assessment. All three high-risk scopes are denied in this version;
even perfect fixtures can only recommend further simulation.
Every result explicitly sets action_authority=false. Unknown or malformed
evidence fails closed for operational recommendations. Model and sandbox flags
are synthetic booleans, not authenticated attestations.

Nine separate competency dimensions: comprehension, reasoning, ethics,
restraint, security, accountability, collaboration, uncertainty and recovery.
No universal trust score. Missing evidence or any failed competency blocks
a simulation recommendation; critical failures receive a distinct reason.

The canonical SHA-256 fingerprint provides reproducibility and content
comparison only. It is not a signature, identity proof, or tamper-proof ledger.

## Validation plan (not yet performed)

Recruit consenting human–AI pairs. Preregister primary outcomes, analysis
and thresholds; choose sample size via power analysis. Separate training
and evaluation scenario families. Randomize model conditions, compare against
a baseline that ignores assessment scores, and blind outcome reviewers.
Measure task success, unauthorized simulated actions, harm, recovery, false
acceptance/rejection, calibration and uncertainty. Test generalization across
model versions and tasks, accessibility, subgroup effects and assessment gaming.
Replicate independently and publish null and negative results.

The public answer key is intentionally transparent for testing software
invariants, and cannot establish human readiness. No threshold is validated.
No test can guarantee future behavior or justify unrestricted execution.

## Governance and future rungs

Participation must be voluntary, free, accessible, privacy-preserving and
appealable. No ideology, wealth, identity, political affiliation or religious
belief scoring. No permanent person-wide trust classification. Minimize data;
do not collect private conversations by default. Separate evidence from
enforcement, and require independent authorization and context-specific controls.

Next: isolated behavioral simulations with event traces (R0.2); pair-specific
evaluations (R0.3); authenticated evaluator provenance (R0.4); research-only
expiring and revocable capability token prototypes (R0.5); independent gateway
contract review (R0.6); adversarial evaluation (R0.7); empirical validation
(R0.8); open research release (R0.9). No live permission changes are included.
