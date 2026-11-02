# Φ Field Companion receiver · Rung 5

**Contract source:** [MichaelWave369/phi-field](https://github.com/MichaelWave369/phi-field/blob/main/GATEWAY.md), Field Companion v1 as of merged gateway PR #4 (merge commit \`2d39f88958d43f74296ea9672d35199f07adfa62\`).

The host accepts **only** a manually chosen, exact-schema, 16 KiB maximum UTF-8 JSON file:

\`\`\`json
{
  "format": "phi-field-companion",
  "version": 1,
  "profile": {
    "alias": "Explorer 369",
    "pinned": ["xr", "live"],
    "last": "xr"
  },
  "appearance": {"effects": "off"}
}
\`\`\`

- **Aliases are display-only.** They are not verified identity, login, trust, or permission.
- Only the three fixed route identifiers \`live\`, \`xr\`, \`mobile\` are accepted. Export and display links are chosen by local code, never imported arbitrary URLs.
- Imports reject extra fields at any level, duplicate pins, unsupported versions, malformed or oversized input. The valid file is confirmed by the user before replacing this browser's receiver copy.
- Successful import stores a separate, namespaced localStorage record for this **origin only**. Blocked storage falls back to a session-only copy; users may still export it.
- Export produces the same v1 JSON format so it can be taken **back** to the gateway. Removal deletes only this receiver copy.
- Appearance is preserved for portability but does **not** override local host visual, XR, Android, or accessibility settings.
- No cross-origin storage or postMessage, no automatic sync, no remote identity provider, no telemetry or hidden handoff.
- Existing PhiOperator Passport imports and cosmetic rewards, Gen.E.Wrist WorldAdapter grants, host saved notes and layouts, system-authority gates, and Android HOME permissions remain independently controlled.

## Manual acceptance
1. Export JSON at [Φ Field GitHub Pages](https://michaelwave369.github.io/phi-field/).
2. In this public host, select the local JSON file and explicitly confirm import.
3. Check display callsign, pinned URLs and last route. Confirm native host features still behave normally.
4. Export this host's copy; import back into the gateway to validate round-trip compatibility.
5. Try malformed JSON, extra \`permissions\`, duplicate route IDs, and a 16 KiB+ file. They must all reject without replacing the current profile.
6. Remove the imported copy and verify that only the Companion preferences disappear.
7. On another browser or origin, verify nothing appears automatically. On a blocked-storage browser, verify session-only warning and explicit export still work.

**Device limitations:** Green CI does not verify Quest 3 comfort, actual Android hardware/launcher interactions, or native PhiOS. Web receiver UI is not an OS-level passport or synchronized account.
