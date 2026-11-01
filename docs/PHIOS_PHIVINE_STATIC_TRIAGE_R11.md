# PhiOS Rung 11 — read-only ΦVine static dependency review

**Status: HELD / untrusted evidence only. No app install or Windows execution.**

PhiVine Rung 10 adds a bounded `phivine triage-imports` command that
recognizes some direct PE import DLL names as prompts for manual review.
This PhiOS rung consumes those **versioned JSON observations** without
downloading the original program, querying Wine, contacting network services
or granting anything.

## Local review

```sh
# PhiVine is optional and external to PhiOS; no shared process is needed.
PYTHONPATH=src python -m phivine triage-imports ./old-app.exe > triage.json
# PhiVine exits 3 (HELD) even when the scan succeeds.

phi-app review-phivine-triage triage.json
# PhiOS also exits 3 and returns a HELD display-only record.
```

The reader accepts the exact `phivine.import_triage.v0.1` shape from
PhiVine merged commit `7c9791c6be75e5f069d513db788627e81405d6d1`.
It checks bounded file length, duplicate JSON keys, a conservative
DLL-basename subset, exact scan scope and non-authority flags, counts and
classification membership. It does not treat the reviewed input as a
signature or immutable program identity; arbitrary local users can construct
similar JSON.

### Display-only output

`phios.phivine_import_triage_review.v0.1` contains only held status,
observed filename/digest, a short list of manually-reviewable categories,
and unclassified imported DLL names. The category descriptions are
supplied by PhiOS's own review UI, not treated as trusted code or arbitrary
instructions from the untrusted JSON.

All of the following remain **false**, even for internally consistent input:

- app registry read/modified; PhiOS install or launch
- network permission granted; user approval or effect lease
- Windows binary file access by PhiOS, Wine execution, compatibility verification
- immutable source, release or sandbox qualification

The parser refuses unknown input fields, duplicate JSON object keys,
unexpected category labels, mismatched counts, changed dependency scan
scope, forged approval flags and any category that claims a DLL outside
the known name catalog.

The current source parser does **not** inspect imported symbols,
delay-loading, dynamic library loads, .NET assemblies, SxS manifests or
MSI installation behavior. Recognized names **do not** mean installed,
available, safe or compatible.

### Independent acceptance

The dedicated GitHub Actions workflow checks out the exact reviewed
PhiVine producer (read-only) and actually invokes its Rung 10 triage CLI
against a locally generated nonfunctional PE32+ fixture with `D3D11.dll`
and `WS2_32.dll` imports. It then invokes the PhiOS CLI and confirms
`HELD`, exit 3. Mutated authority flags and fabricated category claims
must be refused. No executable or untrusted input is launched and only
the short non-authorizing JSON receipt is uploaded.

**No compatibility grade or launch path has been added.**
Separate review gates are still required for binary origin and exact
hash binding, restricted broker, real sandbox/identity controls, explicit
operator approval, effect-bound leases, process lifecycle and independent
post-effect verification.

**Ledger Above Ego. DONE Means Verified.**
