/**
 * Φ FIELD Companion v1 portability receiver.
 * Pinned to the public phi-field v1 JSON contract, NOT PhiOperator Passport.
 * Readable preference file only. Never credentials, authority, or auto-sync.
 */
export const FIELD_FORMAT = 'phi-field-companion';
export const FIELD_VERSION = 1;
export const FIELD_MAX_BYTES = 16 * 1024;
export const FIELD_STORAGE_KEY = 'phi-field:receiver:v1';
export const FIELD_ROUTES = Object.freeze({
  live: 'https://michaelwave369.github.io/PhiOS/',
  xr: 'https://michaelwave369.github.io/PhiOS-XR/',
  mobile: 'https://michaelwave369.github.io/PhiOS-Mobile/'
});
const ROUTES = Object.keys(FIELD_ROUTES);
const plain = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const exact = (obj, keys) => plain(obj) &&
  Object.keys(obj).length === keys.length &&
  keys.every(key => Object.prototype.hasOwnProperty.call(obj, key));

export function validateFieldCompanion(raw) {
  if (!exact(raw, ['format','version','profile','appearance']) ||
      raw.format !== FIELD_FORMAT || raw.version !== FIELD_VERSION ||
      !exact(raw.profile, ['alias','pinned','last']) ||
      !exact(raw.appearance, ['effects']))
    throw new TypeError('Unsupported Field Companion v1 format.');
  const {alias, pinned, last} = raw.profile;
  if (typeof alias !== 'string' || alias.length > 32 ||
      /[\u0000-\u001f\u007f<>]/.test(alias) ||
      !Array.isArray(pinned) || pinned.length > ROUTES.length ||
      pinned.some(x => typeof x !== 'string' || !ROUTES.includes(x)) ||
      new Set(pinned).size !== pinned.length ||
      (last !== null && !ROUTES.includes(last)) ||
      !['on','off'].includes(raw.appearance.effects))
    throw new TypeError('Invalid Field Companion preferences.');
  return {
    format: FIELD_FORMAT,
    version: FIELD_VERSION,
    profile: {alias, pinned: [...pinned], last},
    appearance: {effects: raw.appearance.effects}
  };
}

export function parseFieldCompanion(text) {
  if (typeof text !== 'string' || new TextEncoder().encode(text).byteLength > FIELD_MAX_BYTES)
    throw new TypeError('Field Companion JSON must be under 16 KiB.');
  return validateFieldCompanion(JSON.parse(text));
}

export function createFieldCompanionReceiver({storage = null, key = FIELD_STORAGE_KEY} = {}) {
  let record = null;
  let persisted = false;
  try {
    const text = storage?.getItem?.(key);
    if (text) {record = parseFieldCompanion(text); persisted = true;}
  } catch { /* malformed or unavailable storage cannot break the host */ }
  const snapshot = () => record ? validateFieldCompanion(record) : null;
  return Object.freeze({
    snapshot,
    persisted: () => persisted,
    importJSON(text) {
      const candidate = parseFieldCompanion(text); // validate before altering anything
      record = candidate;
      persisted = false;
      try {
        if (storage?.setItem) {
          storage.setItem(key, JSON.stringify(candidate));
          persisted = true;
        }
      } catch { /* keep session-only copy, export remains available */ }
      return {record: snapshot(), persisted};
    },
    exportJSON() {return record ? JSON.stringify(record, null, 2) + '\n' : null;},
    clear() {
      record = null;
      persisted = false;
      try {storage?.removeItem?.(key);} catch { /* local state is still removed */ }
    }
  });
}
