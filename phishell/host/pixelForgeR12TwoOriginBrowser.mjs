// Actual TWO-ORIGIN PhiOS + PixelForge compiled browser acceptance.
// PixelForge checked out at the exact reviewed merge commit; test uses only synthetic
// identity metadata, disposable 127.0.0.1 origins and an isolated Chrome profile.
import assert from "node:assert/strict";
import {spawn,spawnSync} from "node:child_process";
import {createServer} from "node:http";
import {mkdtemp,readFile,rm,stat} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join,resolve,sep,extname} from "node:path";
import {createHash} from "node:crypto";
import {setTimeout as sleep} from "node:timers/promises";

// R16 optional, explicit CI-only live Pages audit. The default still tests
// the independently assembled, pinned local artifact; the live mode never
// changes PhiOS build-time defaults or makes any app trusted in production.
const useLivePages=process.env.PHIOS_R16_LIVE_PAGES==="1";
const livePixelForgeOrigin="https://michaelwave369.github.io";
const pixelRoot=resolve(".interop/pixelforge/dist");
const pixelSourceRoot=resolve(".interop/pixelforge/vr-studio");
const pixelPublishedBase="/parallax-pixelforge/";
const pixelPublishedStudioPath=pixelPublishedBase+"vr-studio/";
const hostRoot=resolve("phishell/dist");
const pinnedPixelForgeSHA="b1c6314da005de801ba3b0417ffe4b4abe461828";
const sha=spawnSync("git",["-C",resolve(".interop/pixelforge"),"rev-parse","HEAD"],
  {encoding:"utf8"});
assert.equal(sha.status,0,"Pinned PixelForge source checkout required");
assert.equal(sha.stdout.trim(),pinnedPixelForgeSHA,"PixelForge source drift: review new SHA first");
const chrome=[process.env.CHROME_BIN,"google-chrome","chromium","chromium-browser"]
  .filter(Boolean).find(x=>spawnSync(x,["--version"],{encoding:"utf8"}).status===0);
if(!chrome)throw Error("Actual Chrome/Chromium required for cross-origin acceptance");
const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",
  ".svg":"image/svg+xml",".json":"application/json",".png":"image/png",".woff":"font/woff"};
function serve(root,published=false){
  return createServer(async(req,res)=>{
    try{
      const url=new URL(req.url,"http://127.0.0.1");
      const pathname=decodeURIComponent(url.pathname);
      if(published && !pathname.startsWith(pixelPublishedBase)){
        res.writeHead(404).end("Not on published PixelForge Pages route");return;
      }
      const relative=published ? pathname.slice(pixelPublishedBase.length)
        : pathname.slice(1);
      const target=relative && !relative.endsWith("/") ? relative : relative+"index.html";
      const path=resolve(root,target);
      if(path!==join(root,"index.html")&&!path.startsWith(root+sep)){
        res.writeHead(403).end("Blocked");return;
      }
      if(!(await stat(path)).isFile()) {
        res.writeHead(404).end("Missing published file");return;
      }
      res.writeHead(200,{"Content-Type":mime[extname(path)]||"application/octet-stream",
        "Cache-Control":"no-store"}).end(await readFile(path));
    }catch{res.writeHead(404).end("Not found");}
  });
}
const hostServer=serve(hostRoot),pixelServer=serve(pixelRoot,true);
let child=null,socket=null,requestId=0,errors="";
const pending=new Map();
const profile=await mkdtemp(join(tmpdir(),"phios-pixel-two-origin-"));
async function waitFor(label,fn,timeout=28000){
  const end=Date.now()+timeout;let error="";
  while(Date.now()<end){
    try{const result=await fn();if(result)return result;}catch(e){error=e.message;}
    await sleep(110);
  }
  throw Error("R12 browser timeout: "+label+" "+error+" "+errors);
}
function send(method,params={},sessionId){
  const id=++requestId;
  return new Promise((ok,fail)=>{
    const t=setTimeout(()=>{pending.delete(id);fail(Error("CDP timeout "+method));},19000);
    pending.set(id,{ok(v){clearTimeout(t);pending.delete(id);ok(v);},
      fail(e){clearTimeout(t);pending.delete(id);fail(e);}});
    socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
  });
}
const office={providerAppId:"phioffice",source:"phioffice369.project_manifest.v0.1",
  title:"Office private label",projectRef:"project:same-project"};
const pixel={providerAppId:"pixelforge",source:"pixelforge.phios-vr-world-identity.v0.1",
  title:"Private PixelForge World",projectRef:"project:same-project"};
const v2=JSON.stringify({format:"phios.project-registry",version:2,
  entries:[office,pixel]})+"\n";
try{
  await Promise.all([hostServer,pixelServer].map(s=>
    new Promise(ok=>s.listen(0,"127.0.0.1",ok))));
  const hostOrigin="http://127.0.0.1:"+hostServer.address().port;
  const pixelOrigin=useLivePages ? livePixelForgeOrigin
    : "http://127.0.0.1:"+pixelServer.address().port;
  assert.notEqual(hostOrigin,pixelOrigin,"Distinct origins are mandatory");
  // Verify the actual PUBLIC PAGES artifact contains the exact pinned
  // reviewed browser client, without any substituted script bytes.
  for(const file of ["index.html","studio.js","phios-bridge-client.js","phios-bridge-ui.js"]){
    const published=await readFile(join(pixelRoot,"vr-studio",file));
    const source=await readFile(join(pixelSourceRoot,file));
    assert.equal(createHash("sha256").update(published).digest("hex"),
      createHash("sha256").update(source).digest("hex"),
      "Published PixelForge studio artifact drift: "+file);
  }
  let liveHeaderReceipt=null;
  if(useLivePages){
    // A public deployment is a *different* supply chain from locally built
    // Pages. Fetch only the reviewed public HTTPS host and exact static paths.
    // No accounts, cookies, bearer tokens, user worlds or credentials.
    const urlBase=pixelOrigin+pixelPublishedStudioPath;
    async function getPublicAsset(name){
      const address=urlBase+name;
      const response=await fetch(address,{
        method:"GET",redirect:"manual",
        headers:{"Accept":"text/html,application/javascript;q=0.9,*/*;q=0.2"},
        signal:AbortSignal.timeout(20000),
      });
      assert.equal(response.status,200,
        "Live PixelForge expected HTTP 200 without redirect: "+name+
        " received "+response.status);
      assert.equal(response.url,address,"Live PixelForge URL redirected unexpectedly");
      const bytes=Buffer.from(await response.arrayBuffer());
      assert.ok(bytes.length>30 && bytes.length<5000000,
        "Live PixelForge public asset empty or oversized: "+name);
      return {response,bytes};
    }
    const page=await getPublicAsset("index.html");
    const contentType=page.response.headers.get("content-type")||"";
    assert.match(contentType,/text\/html/i,
      "Live PixelForge VR route must return HTML, not a fallback/error");
    assert.ok(page.bytes.toString("utf8").includes("phiosBridgePanel"),
      "Live PixelForge VR Studio has no reviewed bridge controls");
    for(const name of ["phios-bridge-client.js","phios-bridge-ui.js"]){
      const remote=await getPublicAsset(name);
      const reviewed=await readFile(join(pixelSourceRoot,name));
      assert.equal(createHash("sha256").update(remote.bytes).digest("hex"),
        createHash("sha256").update(reviewed).digest("hex"),
        "Live PixelForge client differs from merged #89 source: "+name);
    }
    liveHeaderReceipt={
      url:urlBase,
      httpStatus:page.response.status,
      contentType,
      xFrameOptions:page.response.headers.get("x-frame-options"),
      contentSecurityPolicy:page.response.headers.get("content-security-policy"),
      referrerPolicy:page.response.headers.get("referrer-policy"),
      publishedBridgeBytesMatchMergedSource:true,
    };
    console.log("PHIOS_R16_PIXELFORGE_LIVE_HTTP:"+JSON.stringify(liveHeaderReceipt));
  }
  const build=spawnSync("npm",["run","build"],{
    cwd:resolve("phishell"),encoding:"utf8",timeout:180000,maxBuffer:20*1024*1024,
    env:{...process.env,VITE_PHIOS_PIXELFORGE_BRIDGE_URL:pixelOrigin+pixelPublishedStudioPath,
      VITE_PHIOS_PIXELFORGE_BRIDGE_APPROVED_ORIGIN:pixelOrigin},
  });
  assert.equal(build.status,0,"Compiled PhiOS host build failed:\n"+
    (build.stdout||"").slice(-1700)+"\n"+(build.stderr||"").slice(-1700));
  assert.ok((await stat(join(hostRoot,"index.html"))).isFile());
  child=spawn(chrome,["--headless=new","--no-sandbox","--disable-dev-shm-usage",
    "--disable-background-networking","--disable-extensions","--disable-sync",
    "--no-first-run","--enable-unsafe-swiftshader","--remote-debugging-port=0",
    "--remote-debugging-address=127.0.0.1","--user-data-dir="+profile,"about:blank"],
    {stdio:["ignore","ignore","pipe"]});
  child.stderr.on("data",p=>{errors=(errors+p).slice(-1800);});
  const ws=await waitFor("Chrome DevTools",async()=>{
    if(child.exitCode!==null)throw Error("Chrome exited");
    const parts=(await readFile(join(profile,"DevToolsActivePort"),"utf8").catch(()=>""))
      .trim().split("\n");
    return /^\d+$/.test(parts[0])&&/^\/devtools\/browser\/[a-f0-9-]+$/i.test(parts[1])
      ?"ws://127.0.0.1:"+parts[0]+parts[1]:null;
  });
  socket=new WebSocket(ws);
  await new Promise((ok,fail)=>{
    socket.addEventListener("open",ok,{once:true});
    socket.addEventListener("error",fail,{once:true});
  });
  socket.addEventListener("message",e=>{
    const msg=JSON.parse(e.data),p=pending.get(msg.id);
    if(!p)return;
    if(msg.error)p.fail(Error(msg.error.message));else p.ok(msg.result);
  });
  // Discover cross-site OOPIF targets as well as top-level pages.
  await send("Target.setDiscoverTargets",{discover:true});
  const {targetInfos}=await send("Target.getTargets");
  const page=targetInfos.find(x=>x.type==="page");
  assert.ok(page,"Page target missing");
  const {sessionId}=await send("Target.attachToTarget",
    {targetId:page.targetId,flatten:true});
  await send("Page.enable",{},sessionId);
  await send("Runtime.enable",{},sessionId);
  const call=(method,params={})=>send(method,params,sessionId);
  const evaluate=async(code,contextId)=>{
    // HTTPS GitHub Pages runs in an out-of-process iframe on Chromium.
    // Loopback-only child contexts belong to the parent page session.
    const remoteSession=typeof contextId==="object" ? contextId?.sessionId : null;
    const r=await send("Runtime.evaluate",{expression:code,returnByValue:true,
      awaitPromise:true,...(typeof contextId==="number"?{contextId}:{})},
      remoteSession||sessionId);
    if(r.exceptionDetails)throw Error("Chrome expression: "+
      JSON.stringify(r.exceptionDetails).slice(0,400));
    return r.result?.value;
  };
  const childExecutionContext=async(frameId,worldName)=>{
    try{
      const {executionContextId}=await call("Page.createIsolatedWorld",{
        frameId,worldName,
      });
      return executionContextId;
    }catch(error){
      if(!useLivePages)throw error;
      const targets=await send("Target.getTargets");
      const target=targets.targetInfos.find(x=>x.type==="iframe"&&
        x.url?.startsWith(pixelOrigin+pixelPublishedStudioPath));
      assert.ok(target,"Live PixelForge cross-site iframe target not discoverable");
      const {sessionId:childSession}=await send("Target.attachToTarget",{
        targetId:target.targetId,flatten:true,
      });
      await send("Runtime.enable",{},childSession);
      return {sessionId:childSession};
    }
  };
  const click=(selector,label,contextId)=>evaluate("(()=>{const root=document.querySelector("+
    JSON.stringify(selector)+");const button=Array.from(root?.querySelectorAll('button')||[])"+
    ".find(x=>x.textContent?.trim()==="+JSON.stringify(label)+");"+
    "if(!button||button.disabled)return false;button.click();return true;})()",contextId);
  const frameFor=(origin,frameTree)=>{
    if(frameTree.frame?.url?.startsWith(origin))return frameTree.frame.id;
    for(const c of frameTree.childFrames||[]){
      const found=frameFor(origin,c);if(found)return found;
    }
    return null;
  };
  // Standalone PixelForge remains disconnected, with a hidden panel.
  await call("Page.navigate",{url:pixelOrigin+pixelPublishedStudioPath});
  await waitFor("standalone PixelForge UI",()=>evaluate(
    'Boolean(document.getElementById("phiosBridgePanel"))'));
  assert.equal(await evaluate('document.getElementById("phiosBridgePanel").hidden'),true);
  assert.equal(await evaluate("localStorage.getItem('pixelforge.vr-world.v1.local')"),null);
  // Now browse actual compiled PhiOS on the OTHER origin.
  await call("Page.navigate",{url:hostOrigin+"/"});
  await waitFor("compiled PhiShell",()=>evaluate(
    'Boolean(document.querySelector(".search-button"))'));
  assert.equal(await evaluate('document.querySelector(".phios-pixelforge-bridge iframe")===null'),true,
    "PixelForge must not load without operator action");
  await evaluate("localStorage.setItem("+JSON.stringify("phios.project-registry.v2")+
    ","+JSON.stringify(v2)+")");
  // R14: a real PixelForge launcher tile opens only the governed Build
  // workspace, never an iframe, a grant or an "installed app" claim.
  assert.equal(await evaluate('(()=>{const b=document.querySelector('+
    JSON.stringify('button[aria-label="PixelForge · Browser pilot · gated"]')+
    ');if(!b)return false;b.click();return true;})()'),true,
    "PixelForge browser pilot launcher must be visible on PhiOS Home");
  await waitFor("PixelForge Build workspace",()=>evaluate(
    'Boolean(document.querySelector(".phios-pixelforge-bridge"))'));
  assert.equal(await evaluate(
    'document.querySelector(".phios-pixelforge-bridge iframe")===null'),true,
    "Launcher must not auto-start PixelForge iframe");
  assert.equal(await evaluate(
    'document.querySelector(".phios-pixelforge-bridge [role=status]")?.textContent'), 
    "Not connected. No PixelForge project approval.");
  assert.equal(await click(".phios-pixelforge-bridge","Start PixelForge pilot"),true);
  let observedIframeTargets=[];
  const childFrameId=await waitFor("PixelForge independently loaded frame",async()=>{
    const r=await call("Page.getFrameTree");
    const inParentTree=frameFor(pixelOrigin,r.frameTree);
    if(inParentTree)return inParentTree;
    if(!useLivePages)return null;
    // Different-site HTTPS children are often out-of-process iframe
    // Targets, absent from the top-level Page.getFrameTree result.
    const targets=await send("Target.getTargets");
    observedIframeTargets=targets.targetInfos.filter(x=>x.type==="iframe")
      .map(x=>({targetId:x.targetId,url:x.url?.slice(0,200)}));
    const remote=targets.targetInfos.find(x=>x.type==="iframe"&&
      x.url?.startsWith(pixelOrigin+pixelPublishedStudioPath));
    return remote?.targetId||null;
  });
  let childContext=await childExecutionContext(childFrameId,"PixelForgeR12FirstSession");
  const clientText=()=>evaluate('document.querySelector("#phiosBridgePanel")?.textContent||""',
    childContext);
  await waitFor("child visible and connected",async()=>
    (await clientText()).includes("Connected; no project reference approved yet"),16000);
  const verifiedFrameURL=await evaluate(
    'document.querySelector(".phios-pixelforge-bridge iframe").src');
  assert.ok(verifiedFrameURL.startsWith(pixelOrigin+pixelPublishedStudioPath+"?phios_parent_origin="));
  assert.ok(!verifiedFrameURL.includes("project:same-project"),
    "Project ref must never travel through iframe URL");
  assert.equal(await evaluate('document.querySelector("#phiosBridgePanel").hidden',childContext),false);

  // A real bridge request before approval must be explicitly denied.
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("default denial in PixelForge",async()=>
    (await clientText()).includes("Project request denied; operator approval required"));
  assert.ok(!(await clientText()).includes("Received project ID:"));
  // The only selectable item is the provider-isolated PixelForge record.
  const choices=await evaluate(
    'Array.from(document.querySelector("#phios-pixelforge-bridge-choice").options)'+
    '.map(x=>({value:x.value,label:x.textContent}))');
  assert.equal(choices.length,2);
  assert.ok(choices[1].label.includes("Private PixelForge World"));
  assert.ok(!choices[1].label.includes("Office private label"));
  assert.equal(await evaluate('(()=>{const s=document.querySelector("#phios-pixelforge-bridge-choice");'+
    's.value="project:same-project";s.dispatchEvent(new Event("change",{bubbles:true}));return true;})()'),true);
  await waitFor("operator selected reviewed PixelForge ref",()=>evaluate(
    'document.querySelector(".phios-pixelforge-bridge [role=status]")'+
    '?.textContent?.includes("explicit approval still required")'));
  // A dismissed confirmation must have zero effect.
  await evaluate('window.confirm=()=>false');
  assert.equal(await click(".phios-pixelforge-bridge","Approve selected PixelForge ref"),true);
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("cancelled approval denied",async()=>
    (await clientText()).includes("Project request denied; operator approval required"));
  await evaluate('window.confirm=()=>true');
  assert.equal(await click(".phios-pixelforge-bridge","Approve selected PixelForge ref"),true);
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("approved reference actually crosses",async()=>
    (await clientText()).includes("Received project ID: project:same-project"));
  assert.ok(!(await clientText()).includes("Office private label"));
  assert.ok(!(await clientText()).includes("Private PixelForge World"),
    "Only opaque project ref, not title, can cross via the bridge panel");
  assert.equal(await evaluate("localStorage.getItem('pixelforge.vr-world.v1.local')",childContext),
    null,"Bridge may never save a PixelForge world");

  // R13: even a VALID change to an unrelated V2 identity requires fresh
  // consent. An operator's old approval was scoped to the reviewed registry
  // snapshot; changing another app's metadata cannot silently extend it.
  const changedV2=JSON.stringify({format:"phios.project-registry",version:2,
    entries:[office,pixel,{
      providerAppId:"pixelforge",
      source:"pixelforge.phios-vr-world-identity.v0.1",
      title:"Second World",
      projectRef:"project:second-world",
    }]})+"\n";
  await evaluate("localStorage.setItem("+JSON.stringify("phios.project-registry.v2")+
    ","+JSON.stringify(changedV2)+")");
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("metadata drift revoked former approval",async()=>
    (await clientText()).includes("Project request denied; operator approval required"));
  await waitFor("host explicitly reports consent expiration",()=>evaluate(
    'document.querySelector(".phios-pixelforge-bridge [role=status]")'+
    '?.textContent?.includes("fresh PixelForge consent required")'));
  assert.ok(!(await clientText()).includes("Received project ID:"),
    "A changed V2 registry must erase previously displayed permission context");
  // Restoring the old bytes is NOT permission reinstatement.
  await evaluate("localStorage.setItem("+JSON.stringify("phios.project-registry.v2")+
    ","+JSON.stringify(v2)+")");
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("restored V2 still requires reapproval",async()=>
    (await clientText()).includes("Project request denied; operator approval required"));
  assert.equal(await click(".phios-pixelforge-bridge","Approve selected PixelForge ref"),true);
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("fresh consent after metadata drift",async()=>
    (await clientText()).includes("Received project ID: project:same-project"));

  assert.equal(await click(".phios-pixelforge-bridge","Revoke PixelForge approval"),true);
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("revoked request denied",async()=>
    (await clientText()).includes("Project request denied; operator approval required"));
  assert.ok(!(await clientText()).includes("Received project ID:"),
    "Child should clear its previous label after denial");

  // Host reconnect must produce a new iframe session with NO inherited grant.
  assert.equal(await click(".phios-pixelforge-bridge","Disconnect PixelForge pilot"),true);
  await waitFor("iframe gone",()=>evaluate(
    'document.querySelector(".phios-pixelforge-bridge iframe")===null'));
  assert.equal(await click(".phios-pixelforge-bridge","Start PixelForge pilot"),true);
  const secondFrame=await waitFor("fresh PixelForge frame",async()=>{
    const t=await call("Page.getFrameTree");return frameFor(pixelOrigin,t.frameTree);
  });
  childContext=await childExecutionContext(secondFrame,"PixelForgeR12Reconnect");
  await waitFor("fresh handshake not pre-approved",async()=>
    (await clientText()).includes("Connected; no project reference approved yet"),16000);
  assert.equal(await click("#phiosBridgePanel","Request project reference",childContext),true);
  await waitFor("reconnected denied until new approval",async()=>
    (await clientText()).includes("Project request denied; operator approval required"));
  assert.equal(await evaluate("localStorage.getItem('phios.project-registry.v2')"),v2,
    "No approval or provider identity may mutate V2");
  assert.equal(await evaluate("localStorage.getItem('phios.project-registry.v1')"),null,
    "The PixelForge pilot may not create PhiOffice V1 registry");

  console.log("PHIOS_R12_PIXELFORGE_TWO_ORIGIN_CHROME:"+JSON.stringify({
    schema:"phios.r12.two_origin_pixel_bridge.v0.1",
    phiOSCommit:process.env.GITHUB_SHA||null,
    pixelForgeCommit:pinnedPixelForgeSHA,
    twoIndependentOrigins:hostOrigin!==pixelOrigin,
    pixelForgeServedFromAssembledPages:!useLivePages,
    pixelForgeServedFromActualPublicPages:useLivePages,
    livePublicHeaderEvidence:liveHeaderReceipt,
    githubProjectPagesPath:pixelPublishedStudioPath,
    reviewedStudioScriptsByteIdentical:true,
    standaloneNoBridge:true,
    launcherOpenedBuildOnly:true,
    launcherGrantedPermission:false,
    deniedBeforeApproval:true,
    cancelledApprovalDenied:true,
    exactProviderIdentityShared:true,
    validV2DriftRevoked:true,
    restoredV2DidNotRestoreApproval:true,
    explicitReapprovalRequired:true,
    revokedFutureRequests:true,
    reconnectDenied:true,
    phiOfficeApprovalInherited:false,
    v2Changed:false,
    worldFilesTransferred:0,
    nativeInstalled:false,
    publisherAuthenticated:false,
  }));
} finally {
  if(socket?.readyState===WebSocket.OPEN){try{await send("Browser.close");}catch{}socket.close();}
  if(child?.exitCode===null)child.kill("SIGTERM");
  await Promise.all([hostServer,pixelServer].map(s=>new Promise(ok=>s.close(ok))));
  await rm(profile,{recursive:true,force:true,maxRetries:4,retryDelay:100});
}
