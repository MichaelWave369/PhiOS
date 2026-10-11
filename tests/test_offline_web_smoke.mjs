import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,symlink,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {options,localPath,installedRoot,loopbackServer} from "../scripts/offline_web_smoke.mjs";

test("strict five-argument CLI and reviewed keys",()=>{
  const valid=["--app","vessie-web","--trellis-home","/tmp/a","--chrome","/usr/bin/chromium",
    "--playwright-root","/tmp/b","--report","/tmp/out.json"];
  assert.equal(options(valid)["--app"],"vessie-web");
  assert.throws(()=>options(valid.slice(0,-2)),/SMOKE_MISSING/);
  assert.throws(()=>options([...valid,"--app","evil"]),/SMOKE_INVALID/);
  assert.throws(()=>options(valid.map(x=>x==="vessie-web"?"evil":x)),/SMOKE_UNREVIEWED_APP/);
});
test("path traversal and hidden files are rejected",()=>{
  const root="/tmp/phios-static";
  assert.equal(localPath(root,"/"),join(root,"index.html"));
  assert.equal(localPath(root,"/assets/main.js"),join(root,"assets/main.js"));
  for (const path of ["/../outside","/%2e%2e/out","/assets/.secret","/%2fetc/passwd",
    "/assets//evil","/assets/%5c..%5csecret","/%00bad"]) assert.equal(localPath(root,path),null,path);
});
test("only real installed dirs are accepted",async()=>{
  const home=await mkdtemp(join(tmpdir(),"phios-root-"));
  try {
    const dest=join(home,"cellar","phios-vessie-web","0.1.0");
    await mkdir(dest,{recursive:true});
    await writeFile(join(dest,"index.html"),'<div id="root">yes</div>');
    assert.equal(await installedRoot(home,"vessie-web"),dest);
    await assert.rejects(installedRoot(home,"evil"),/SMOKE_UNREVIEWED_APP/);
    const link=home+"-link"; await symlink(home,link);
    try {await assert.rejects(installedRoot(link,"vessie-web"),/SMOKE_HOME_NOT_REAL/);}
    finally {await rm(link);}
  } finally {await rm(home,{recursive:true,force:true});}
});
test("loopback serves bytes but blocks hidden files and missing paths",async()=>{
  const dir=await mkdtemp(join(tmpdir(),"phios-http-"));
  let server;
  try {
    await mkdir(join(dir,"assets"));
    await writeFile(join(dir,"index.html"),'<div id="root">yes</div>');
    await writeFile(join(dir,"assets","main.js"),"console.log('ok')");
    const result=await loopbackServer(dir); server=result.server;
    let r=await fetch(result.origin+"/assets/main.js");
    assert.equal(r.status,200); assert.match(await r.text(),/ok/);
    r=await fetch(result.origin+"/.secret");assert.equal(r.status,403);
    r=await fetch(result.origin+"/absent.js");assert.equal(r.status,404);
  } finally {
    if (server) await new Promise(done=>server.close(done));
    await rm(dir,{recursive:true,force:true});
  }
});
