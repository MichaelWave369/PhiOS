import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {runInNewContext} from "node:vm";

const root = new URL("../", import.meta.url);
const canonical=JSON.parse(await readFile(new URL("../interop/public-repo-catalog.v1.json",root),"utf8"));
const native=JSON.parse(await readFile(new URL("./src/data/public-repo-catalog.v1.json",root),"utf8"));
const canonicalJS=await readFile(new URL("../interop/shelf-portable.v1.js",root),"utf8");
const nativeJS=await readFile(new URL("./public/shelf-portable.js",root),"utf8");
const shell=await readFile(new URL("./src/components/UniversalAppShelf.tsx",root),"utf8");
const launcher=await readFile(new URL("./src/components/AppLauncher.tsx",root),"utf8");
const html=await readFile(new URL("./index.html",root),"utf8");
const ctx={TextEncoder,Date};
runInNewContext(nativeJS,ctx);
const api=ctx.PhiShelf;
const app0=canonical.apps[0],app1=canonical.apps[1];

test("PhiShell bundles the exact public catalog and portable JS used by Web and Mobile",()=>{
  assert.deepEqual(native,canonical);
  assert.equal(nativeJS,canonicalJS);
  assert.equal(native.apps.length,225);
  assert.equal(native.provenance.source_blob_sha,"e295f6265e60032de98a2acd8e53295505fc47e8");
  assert.match(html,/shelf-portable\.js/);
  assert.match(launcher,/UniversalAppShelf/);
});

test("native GUI shelf JSON round-trips as source IDs, not install permissions",()=>{
  const ids=[app0.id,app1.id];
  const packet=api.packet(ids,native,new Date("2026-11-05T22:00:00.000Z"));
  assert.equal(packet.format,"phios-app-shelf");
  assert.equal(packet.version,1);
  assert.equal(packet.catalog_source_sha,native.provenance.source_blob_sha);
  assert.deepEqual(Array.from(api.parse(JSON.stringify(packet),native)),ids);
  assert.deepEqual(Array.from(api.move(ids,ids[1],-1,native)),ids.slice().reverse());
  assert.throws(()=>api.parse(JSON.stringify({...packet,launch_authority:true}),native),/contract/);
  assert.throws(()=>api.pin([], "github:999999999999999",native),/Invalid/);
  assert.match(api.badge(app0),/SOURCE ONLY/);
});

test("visual interface offers explicit export/import, no host or install bridge",()=>{
  assert.match(shell,/localStorage\.setItem\(STORAGE_KEY/);
  assert.match(shell,/api\.parse\(await file\.text\(\), CATALOG\)/);
  assert.match(shell,/globalThis\.confirm/);
  assert.match(shell,/SOURCE BOOKMARKS/);
  assert.match(shell,/View GitHub source/);
  assert.doesNotMatch(shell,/\b(eval|exec|sudo|spawn|npm install|packageInstaller)\b/);
});
