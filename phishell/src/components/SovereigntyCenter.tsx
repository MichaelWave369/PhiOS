import { useState } from "react";

const pillars = [
  ["Data", "Export, verify, and restore complete user-owned application state"],
  ["Compute", "Run local features without a mandatory hosted Phi service"],
  ["Connectivity", "Demonstrate meaningful cold-start offline behavior"],
  ["Knowledge", "Keep readable offline resources with verifiable sources"],
  ["Identity", "Revoke credentials and recover without vendor escrow"],
  ["Skills", "Access human-readable, AI-optional operating instructions"],
  ["Economics", "Fork, self-host, and exit without platform retaliation"],
] as const;

const selfChecks = [
  "I exported the actual data I need, not just a demonstration fixture.",
  "I verified the archive hashes and restored it on another compatible system.",
  "My essential local tools still operate when the Phi services and internet are unavailable.",
  "I can replace the model/provider and retain my records.",
  "I can revoke credentials, understand the result, and recover independently.",
] as const;

function downloadChecklist(checked: string[]) {
  const payload = {
    schema: "phios.sovereignty.self-audit.v0.1",
    warning: "Self-reported checklist. NOT a host attestation, certification, or verification receipt.",
    answers: selfChecks.map((description, index) => ({
      description,
      selfReported: checked.includes(String(index)),
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "my-sovereignty-self-audit.json";
    anchor.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function SovereigntyCenter() {
  const [checked, setChecked] = useState<string[]>([]);
  return (
    <section className="sovereignty-center" aria-label="Sovereignty Center">
      <div className="sovereignty-intro">
        <span className="sovereignty-eyebrow">Φ SOVEREIGNTY CENTER · v0.1</span>
        <h2>Keep your capabilities even if we disappear.</h2>
        <p>
          Your data, tools, memory, and decisions should survive a complete departure
          from PhiOS and Enter the Field. This panel does not inspect your machine or
          certify it. The independent Exit Test is an engineering target, not a green badge.
        </p>
        <div className="sovereignty-banner" role="status">
          <strong>OVERALL: UNVERIFIED</strong>
          <span>No end-to-end offline OS, application migration, or credential-recovery attestation exists here.</span>
        </div>
      </div>
      <div className="sovereignty-columns">
        <div className="sovereignty-group">
          <h3>Seven user rights</h3>
          <div className="sovereignty-pillars">
            {pillars.map(([name, goal]) => (
              <article className="sovereignty-pillar" key={name}>
                <strong>{name}</strong>
                <p>{goal}</p>
                <span>NOT END-TO-END VERIFIED</span>
              </article>
            ))}
          </div>
        </div>
        <div className="sovereignty-group">
          <h3>What works in v0.1</h3>
          <p>
            A standalone, Python-standard-library directory packer creates ordinary ZIP
            archives with SHA-256 manifests. It can verify and restore independently of
            PhiOS. It does not collect all your PhiOS state automatically.
          </p>
          <pre className="sovereignty-commands">{[
            "python scripts/sovereignty_exit_v01.py pack",
            "  --source ./my-data --output ./backup.zip",
            "python scripts/sovereignty_exit_v01.py verify",
            "  --bundle ./backup.zip",
            "python scripts/sovereignty_exit_v01.py unpack",
            "  --bundle ./backup.zip --output ./restored",
          ].join("\n")}</pre>
          <p className="sovereignty-warning">
            The backup is NOT encrypted. Never upload it publicly. Only package directories you chose.
          </p>
          <a className="sovereignty-link" href="https://github.com/MichaelWave369/PhiOS/blob/main/SOVEREIGNTY_CONTRACT.md" target="_blank" rel="noreferrer">
            Read the public sovereignty contract
          </a>
          <a className="sovereignty-link" href="https://github.com/MichaelWave369/PhiOS/blob/main/docs/PHIOS_SOVEREIGNTY_EXIT_V01.md" target="_blank" rel="noreferrer">
            See commands, limits, and reproducible tests
          </a>
        </div>
      </div>
      <div className="sovereignty-self">
        <h3>My personal exit rehearsal</h3>
        <p>Tick only what you tried yourself. These answers stay in this window unless you download them.</p>
        {selfChecks.map((label, index) => {
          const id = String(index);
          return (
            <label className="sovereignty-check" key={id}>
              <input
                type="checkbox"
                checked={checked.includes(id)}
                onChange={(event) => setChecked((old) => event.target.checked
                  ? [...old, id]
                  : old.filter((item) => item !== id))}
              />
              <span>{label}</span>
            </label>
          );
        })}
        <div className="sovereignty-self-footer">
          <strong>Self-reported: {checked.length}/{selfChecks.length}, not independently verified</strong>
          <button type="button" onClick={() => downloadChecklist(checked)}>
            Download my checklist JSON
          </button>
        </div>
      </div>
    </section>
  );
}
