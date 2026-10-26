# Φ Sovereignty Contract v0.1

**Status:** Public, versioned engineering commitment. Not a claim of current conformity.

> The success of this system is measured by the user's ability to leave it without losing their work.

## Rights and non-negotiable rules

1. **Data ownership.** The operator may inspect, export, back up, migrate, and delete their own data. Export formats and schemas must be documented and usable without a Phi service.
2. **No mandatory platform account.** Core local capabilities must not require registration, a subscription, periodic cloud authorization, or a Phi-hosted server.
3. **Model and provider choice.** No single cloud API or Phi model may be a hidden hard dependency for essential local features. Absence or fallback must be reported honestly.
4. **Offline resilience.** Critical local features must be testable with network access denied. Offline cannot be inferred from a successful connected build.
5. **Independent recovery.** Backup verification, format documentation, and restoration instructions must work on a compatible independent environment. Backup creation alone is not proof.
6. **User-controlled security.** The operator can revoke credentials and grants. Keys must not be escrowed in a Phi service without explicit, informed opt-in; secrets must never appear in public evidence.
7. **Fork, repair and inspect.** Project-owned source and formats remain under their published licenses; third-party software and model weights retain their own terms.
8. **No coercive lock-in.** No exit fees, artificial export throttles, or deletion of local data as retaliation for leaving.
9. **Skills before dependence.** Where practical, include human-readable manuals and explanations that let people accomplish essential tasks without AI.
10. **Truthful provenance.** “Implemented,” “verified,” “supported,” and “planned” must remain distinct. UI badges and release gates require reproducible evidence.

## The Φ Exit Test

An app may claim **EXIT-VERIFIED** only when an independent reviewer can:
- Start its essential local functionality with Phi-hosted services unavailable.
- Export a representative complete dataset in an open documented format.
- Verify checksums and restore it to a fresh compatible installation.
- Read the recovered data without a Phi account, service, or special key.
- Replace an optional model/provider and revoke old app credentials.
- Inspect a machine-readable test report containing versions, procedures, dates, and failures.

Partial tests earn only **PARTIAL** or **UNVERIFIED**, never an aggregate “passed” badge.

## Initial implementation boundary

The standalone `scripts/sovereignty_exit_v01.py` operates on an operator-selected local directory with ZIP + SHA-256 manifests and can be used without PhiOS. This **does not** prove that PhiOS application state, credentials, model weights, or all linked projects can already be exported. The current PhiShell Sovereignty Center is an informational dashboard and a user-controlled checklist, not a host audit.

The sample CI tests exercise this portable directory format only, not actual OS cold boot, provider replacement, offline runtime functionality, or disaster recovery.

**Privacy warning:** Exported archives are **not encrypted**. Review source directories before packaging; do not put secrets in public build logs, CI fixtures, or unsecured backups.

## Governance

Any future requirement for a hosted Phi account, cloud lock, telemetry, server-side kill switch, or restriction on export requires explicit review against this contract. A PhiOS feature cannot silently promote its own evidence to authority. This document supplements existing safety and authority contracts; it grants no runtime capability.

See [Exit Test v0.1](docs/PHIOS_SOVEREIGNTY_EXIT_V01.md).
