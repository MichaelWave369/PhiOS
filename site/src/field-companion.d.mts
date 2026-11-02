export type FieldRoute = 'live' | 'xr' | 'mobile';
export type FieldCompanion = {
  format: 'phi-field-companion';
  version: 1;
  profile: {alias: string; pinned: FieldRoute[]; last: FieldRoute | null};
  appearance: {effects: 'on' | 'off'};
};
export declare const FIELD_FORMAT: 'phi-field-companion';
export declare const FIELD_VERSION: 1;
export declare const FIELD_MAX_BYTES: number;
export declare const FIELD_STORAGE_KEY: string;
export declare const FIELD_ROUTES: Readonly<Record<FieldRoute, string>>;
export declare function validateFieldCompanion(raw: unknown): FieldCompanion;
export declare function parseFieldCompanion(text: string): FieldCompanion;
export declare function createFieldCompanionReceiver(options?: {
  storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null;
  key?: string;
}): Readonly<{
  snapshot(): FieldCompanion | null;
  persisted(): boolean;
  importJSON(text: string): {record: FieldCompanion | null; persisted: boolean};
  exportJSON(): string | null;
  clear(): void;
}>;
