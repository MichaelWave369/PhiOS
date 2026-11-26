# GenomeMemory advisory fixture intake v1

Owner: PhiOS. Source base: 43620d38d6164b3579d61784cdb140462501ff1f.
The module accepts a strict nine-check summary from PhiMemory9's Living Memory
fixture demonstration and returns HELD, even if all declared experiments pass.
It records a report fingerprint, not independent evidence verification.

`python -m phios.genomememory_advisory /path/to/advisory.json` exits **3** for
HELD and **2** for invalid input. It has no network, database, application
registration, model, agent execution or memory mutation path. It does not
modify GovernedMemoryService, Reality Ledger or Verification Spine state.

Run `python -m unittest discover -s tests -p test_genomememory_advisory.py -v`.
PhiMemory9's optional native demonstration invokes this real module and checks
the HELD result. Its separate synthetic local HMAC identities are not PhiOS
AuthorityContext, MemoryAccessDecision or execution grants.

Future integration must explicitly bind GenomeMemory native identities,
scope/classification, source provenance, retention and transformation lineage
to the existing phios.memory contracts. Policy resolution still requires
PhiOS authority, and evidence receipts do not promote heuristic confidence.
Production key lifecycle, independent evidence and real-source security remain
blockers. Agentora and PhiBuddy are future explicit operator consumers; this
advisory does not connect them or confer authority.
