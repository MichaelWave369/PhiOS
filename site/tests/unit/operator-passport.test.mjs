import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { parsePortablePassport, summarizePortablePassport, createPortablePassportStore } from "../../public/operator-passport/sdk.js";
const sample = (scores=[])=>JSON.stringify({format:"phioperator-passport",version:1,
  results:scores.map((score,i)=>({rank:i+1,mode:"standard",bestScore:score}))});
test("static PhiOS pilot uses only cosmetic rewards and v1 input",()=>{
 const s=summarizePortablePassport(parsePortablePassport(sample([9,9,9,9,9,9])));
 assert.equal(s.clearedRank,6);
 assert(s.benefits.includes("phios-site-grid"));
 assert(s.benefits.includes("phios-architect-mark"));
 assert.equal(createPortablePassportStore().snapshot().imported,false);
 assert.throws(()=>parsePortablePassport("{not-json"),SyntaxError);
});
test("Passport station ships in public assets and requires local file selection",async()=>{
 const p=new URL("../../public/operator-passport/",import.meta.url);
 const html=await readFile(new URL("index.html",p),"utf8");
 const js=await readFile(new URL("station.js",p),"utf8");
 assert.match(html,/id="passport-file"/);
 assert.match(html,/id="passport-remove"/);
 assert.match(js,/operator\.importJSON\(text\)/);
 assert.match(js,/operator\.clear\(\)/);
 assert.doesNotMatch(js,/fetch\(|requestWorldAction|grant|localStorage\.getItem\("PhiOperator/);
});
