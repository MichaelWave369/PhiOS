import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseFieldCompanion, createFieldCompanionReceiver, FIELD_STORAGE_KEY} from '../../src/field-companion.mjs';

const good = {
  format:'phi-field-companion', version:1,
  profile:{alias:'Explorer 369',pinned:['xr','live'],last:'xr'},
  appearance:{effects:'off'}
};
const json = x => JSON.stringify(x);
test('accepts the exact gateway v1 format and preserves portable preferences', () => {
  assert.deepEqual(parseFieldCompanion(json(good)), good);
  const store = new Map();
  const storage = {
    getItem:k => store.get(k) ?? null,
    setItem:(k,v) => store.set(k,v),
    removeItem:k => store.delete(k)
  };
  const receiver = createFieldCompanionReceiver({storage});
  assert.equal(receiver.snapshot(), null);
  assert.equal(receiver.importJSON(json(good)).persisted, true);
  assert.deepEqual(JSON.parse(receiver.exportJSON()), good);
  assert.equal(store.has(FIELD_STORAGE_KEY),true);
  const next = createFieldCompanionReceiver({storage});
  assert.deepEqual(next.snapshot(),good);
  next.clear();
  assert.equal(store.has(FIELD_STORAGE_KEY),false);
});
test('rejects unknown fields, false authority, duplicates and oversized input without mutation', () => {
  const receiver = createFieldCompanionReceiver();
  receiver.importJSON(json(good));
  const invalid = [
    {...good, permissions:['all']},
    {...good,version:2},
    {...good,profile:{...good.profile,pinned:['xr','xr']}},
    {...good,profile:{...good.profile,last:'https://attacker.invalid/'}},
    {...good,profile:{...good.profile,alias:'<img src=x>'}},
    {...good,appearance:{effects:'off',admin:true}},
    {...good,profile:{alias:'x',pinned:[],last:null,token:'secret'}},
  ];
  for(const item of invalid) assert.throws(()=>receiver.importJSON(json(item)));
  assert.throws(()=>parseFieldCompanion(' '.repeat(16385)));
  assert.deepEqual(receiver.snapshot(),good);
});
test('blocked storage allows session use and export without permission transfer', () => {
  const storage = {getItem(){throw Error('blocked')},setItem(){throw Error('blocked')},removeItem(){throw Error('blocked')}};
  const receiver = createFieldCompanionReceiver({storage});
  assert.equal(receiver.importJSON(json(good)).persisted,false);
  assert.deepEqual(JSON.parse(receiver.exportJSON()),good);
  receiver.clear();
  assert.equal(receiver.snapshot(),null);
});
