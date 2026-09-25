const ALLOWED_KINDS = new Set([
  "symbol",
  "metaphor",
  "question",
  "hypothesis",
  "association",
  "pattern",
  "dream_fragment",
  "creative_seed",
]);

const REQUEST_KEYS = [
  "artifact_kind",
  "content",
  "created_at",
  "evidence_ref_sha256s",
  "parent_artifact_sha256s",
  "tags",
  "title",
];

function sha256(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function canonicalStringArray(value, {
  maxItems,
  itemMax,
  lowercase = false,
  sha = false,
} = {}) {
  if (!Array.isArray(value) || value.length > maxItems) return false;
  const strings = value.every((item) =>
    typeof item === "string" &&
    item.length > 0 &&
    item.length <= itemMax &&
    (!lowercase || item === item.toLowerCase()) &&
    (!sha || sha256(item)),
  );
  if (!strings) return false;
  const uniqueSorted = [...new Set(value)].sort();
  return uniqueSorted.length === value.length &&
    uniqueSorted.every((item, index) => item === value[index]);
}

export function validateCuriosityPersistRequestPayload(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  if (keys.length !== REQUEST_KEYS.length ||
      !keys.every((key, index) => key === REQUEST_KEYS[index])) {
    return false;
  }

  return (
    ALLOWED_KINDS.has(value.artifact_kind) &&
    typeof value.title === "string" &&
    value.title.trim().length > 0 &&
    value.title.length <= 256 &&
    typeof value.content === "string" &&
    value.content.trim().length > 0 &&
    value.content.length <= 32768 &&
    typeof value.created_at === "string" &&
    value.created_at.length <= 64 &&
    !Number.isNaN(Date.parse(value.created_at)) &&
    canonicalStringArray(value.tags, {
      maxItems: 64,
      itemMax: 256,
      lowercase: true,
    }) &&
    canonicalStringArray(value.evidence_ref_sha256s, {
      maxItems: 64,
      itemMax: 64,
      sha: true,
    }) &&
    canonicalStringArray(value.parent_artifact_sha256s, {
      maxItems: 64,
      itemMax: 64,
      sha: true,
    })
  );
}

export function validateCuriosityPersistRequestId(value) {
  return typeof value === "string" &&
    /^curiosity-request-[0-9a-f]{32}$/.test(value);
}
