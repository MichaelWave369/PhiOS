/**
 * ΦOperator Portable Passport SDK v1
 * Dependency-free browser/Node ESM; copy/pin this exact file in offline hosts.
 * A Passport is user-editable game progress, NEVER identity, trust, permission,
 * a credential, or an authorization signal. No networking or side effects.
 */
export const PASSPORT_SCHEMA = Object.freeze({ format: "phioperator-passport", version: 1 });
export const PASSPORT_LIMIT = 16384;
export const PASSPORT_STORAGE_KEY = "phioperator.passport-import.v1";
export const PASSPORT_REWARDS = Object.freeze([
  { id: "phisurf-wheel", rank: 2 },
  { id: "genewrist-pulse", rank: 3 },
  { id: "phios-mobile-halo", rank: 2 },
  { id: "phios-site-grid", rank: 3 },
  { id: "phios-architect-mark", rank: 6 },
].map(x => Object.freeze(x)));

export function validatePortablePassport(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw) ||
      raw.format !== PASSPORT_SCHEMA.format || raw.version !== PASSPORT_SCHEMA.version ||
      !Array.isArray(raw.results) || raw.results.length > 12)
    throw new TypeError("Unsupported ΦOperator Passport version or shape.");
  const seen = new Set();
  const results = raw.results.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry) ||
        !Number.isInteger(entry.rank) || entry.rank < 1 || entry.rank > 6 ||
        !["standard", "chaos"].includes(entry.mode) ||
        !Number.isInteger(entry.bestScore) || entry.bestScore < 0 || entry.bestScore > 9)
      throw new TypeError("Invalid ΦOperator result.");
    const key = entry.mode + ":" + entry.rank;
    if (seen.has(key)) throw new TypeError("Duplicate ΦOperator result.");
    seen.add(key);
    return { rank: entry.rank, mode: entry.mode, bestScore: entry.bestScore };
  });
  return { format: PASSPORT_SCHEMA.format, version: PASSPORT_SCHEMA.version, results };
}

export function parsePortablePassport(text) {
  if (typeof text !== "string" || text.length > PASSPORT_LIMIT)
    throw new TypeError("Passport must be valid JSON under 16 KiB.");
  return validatePortablePassport(JSON.parse(text));
}

export function summarizePortablePassport(raw) {
  if (raw === null) return Object.freeze({
    imported: false, clearedRank: 0, nextRank: 1, benefits: Object.freeze([]),
  });
  const passport = validatePortablePassport(raw);
  let clearedRank = 0;
  for (let rank = 1; rank <= 6; rank++) {
    const score = passport.results.find(r => r.rank === rank && r.mode === "standard")?.bestScore;
    if (score == null || score < 7) break;
    clearedRank = rank;
  }
  return Object.freeze({
    imported: true, clearedRank, nextRank: Math.min(6, clearedRank + 1),
    benefits: Object.freeze(PASSPORT_REWARDS.filter(r => r.rank <= clearedRank).map(r => r.id)),
  });
}

export function createPortablePassportStore({ storage = null, key = PASSPORT_STORAGE_KEY } = {}) {
  let value = null, persisted = false;
  try {
    const existing = storage?.getItem?.(key);
    if (existing) { value = parsePortablePassport(existing); persisted = true; }
  } catch { /* blocked or invalid storage: start with no import */ }
  const snapshot = () => summarizePortablePassport(value);
  return Object.freeze({
    snapshot,
    hasBenefit(id) { return snapshot().benefits.includes(id); },
    importJSON(text) {
      const candidate = parsePortablePassport(text); // validate BEFORE replacing
      value = candidate;
      try {
        if (storage?.setItem) {
          storage.setItem(key, JSON.stringify(candidate)); persisted = true;
        } else persisted = false;
      } catch { persisted = false; }
      return Object.freeze({ ...snapshot(), persisted });
    },
    exportJSON() { return value ? JSON.stringify(value, null, 2) : null; },
    clear() {
      value = null; persisted = false;
      try { storage?.removeItem?.(key); } catch { /* revocation still local */ }
      return snapshot();
    },
  });
}
