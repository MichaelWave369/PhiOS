import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,symlink,rm} from "node:fs/promises";
import {join} from "node:path";
import {tmpdir} from "node:os";
import {offlineRoot,expectedOfflineAction} from "../scripts/disconnected_web_smoke.mjs";
test("only the two fixed harmless offline interactions are recognized",()=>{
  assert.equal(expectedOfflineAction("vessie-web"),"atlas-filter");
  assert.equal(expectedOfflineAction("thinktank-web"),"audit-mode");
  for(const key of ["evil","other","../../evil"])assert.throws(
    ()=>expectedOfflineAction(key),/UNREVIEWED_APP/);
});
test("offline root needs a real, non-symlinked derived install",async()=>{
  const home=await mkdtemp(join(tmpdir(),"phios-disconnected-"));
  const key="vessie-web";
  try{
    const dir=join(home,"cellar","phios-"+key+"-offline","0.1.0");
    await mkdir(dir,{recursive:true});
    for(const name of ["index.html","phios-offline-sw.js","phios-offline-bootstrap.js"])
      await writeFile(join(dir,name),"valid fixture");
    assert.equal(await offlineRoot(home,key),dir);
    await assert.rejects(offlineRoot(home,"not-an-app"),/UNREVIEWED_APP/);
    const symlinkHome=home+"-symlink";await symlink(home,symlinkHome);
    try{await assert.rejects(offlineRoot(symlinkHome,key),/HOME_INVALID/);}
    finally{await rm(symlinkHome);}
  }finally{await rm(home,{recursive:true,force:true});}
});
