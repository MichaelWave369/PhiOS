// Actual compiled PhiShell R11 browser acceptance. No real projects or grants.
import assert from "node:assert/strict";
import {spawn,spawnSync} from "node:child_process";
import {createServer} from "node:http";
import {mkdtemp,readFile,writeFile,rm,stat} from "node:fs/promises";
import {tmpdir} from "node:os";
import {resolve,join,sep,extname} from "node:path";
import {setTimeout as sleep} from "node:timers/promises";

const root=resolve("phishell/dist"),tmp=await mkdtemp(join(tmpdir(),"phios-r11-chrome-"));
const browser=[process.env.CHROME_BIN,"google-chrome","chromium","chromium-browser"]
  .filter(Boolean).find(bin=>spawnSync(bin,["--version"]).status===0);
if(!browser)throw Error("Actual Chrome/Chromium is required");
const office={projectRef:"project:same-project",title:"Office World",
  source:"phioffice369.project_manifest.v0.1"};
const v1=JSON.stringify({format:"phios.project-registry",version:1,entries:[office]})+"\n";
const v2=JSON.stringify({format:"phios.project-registry",version:2,
  entries:[{providerAppId:"phioffice",...office}]})+"\n";
const sidecar={schema:"pixelforge.phios-vr-world-identity.v0.1",
  projectId:"same-project",title:"PixelForge World",
  worldFormat:"pixelforge.vr-world.v1"};
const valid=join(tmp,"good.json"),invalid=join(tmp,"bad.json");
await writeFile(valid,JSON.stringify(sidecar)+"\n");
await writeFile(invalid,JSON.stringify({...sidecar,grant:"read-all"})+"\n");
const mime={".html":"text/html",".js":"text/javascript",".css":"text/css",
  ".svg":"image/svg+xml",".json":"application/json"};
const server=createServer(async(req,res)=>{
  try{
    const uri=new URL(req.url,"http://127.0.0.1");
    let path=resolve(root,decodeURIComponent(uri.pathname.slice(1)||"index.html"));
    if(path!==join(root,"index.html")&&!path.startsWith(root+sep)){
      res.writeHead(403).end();return;
    }
    if(!(await stat(path)).isFile())path=join(root,"index.html");
    res.writeHead(200,{"Content-Type":mime[extname(path)]||"application/octet-stream",
      "Cache-Control":"no-store"}).end(await readFile(path));
  }catch{res.writeHead(404).end();}
});
let child=null,socket=null,seq=0,stderr="";
const pending=new Map();
async function waitFor(label,fn){
  const end=Date.now()+30000;let last="";
  while(Date.now()<end){
    try{const result=await fn();if(result)return result;}catch(e){last=e.message;}
    await sleep(100);
  }
  throw Error("R11 Chrome timeout: "+label+" "+last+" "+stderr);
}
function send(method,params={},sessionId){
  const id=++seq;
  return new Promise((ok,fail)=>{
    const timer=setTimeout(()=>{pending.delete(id);fail(Error("CDP timeout: "+method));},20000);
    pending.set(id,{ok(value){clearTimeout(timer);pending.delete(id);ok(value);},
      fail(error){clearTimeout(timer);pending.delete(id);fail(error);}});
    socket.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
  });
}
try{
  await new Promise(ok=>server.listen(0,"127.0.0.1",ok));
  const origin="http://127.0.0.1:"+server.address().port;
  child=spawn(browser,["--headless=new","--no-sandbox","--disable-dev-shm-usage",
    "--disable-extensions","--disable-background-networking","--disable-sync",
    "--no-first-run","--enable-unsafe-swiftshader","--remote-debugging-port=0",
    "--remote-debugging-address=127.0.0.1","--user-data-dir="+tmp,"about:blank"],
    {stdio:["ignore","ignore","pipe"]});
  child.stderr.on("data",data=>{stderr=(stderr+data).slice(-1300);});
  const endpoint=await waitFor("Chrome DevTools",async()=>{
    if(child.exitCode!==null)throw Error("Chrome exited");
    const parts=(await readFile(join(tmp,"DevToolsActivePort"),"utf8").catch(()=>""))
      .trim().split("\n");
    return /^\d+$/.test(parts[0])&&/^\/devtools\/browser\/[a-f0-9-]+$/i.test(parts[1])
      ?"ws://127.0.0.1:"+parts[0]+parts[1]:null;
  });
  socket=new WebSocket(endpoint);
  await new Promise((ok,fail)=>{
    socket.addEventListener("open",ok,{once:true});
    socket.addEventListener("error",fail,{once:true});
  });
  socket.addEventListener("message",event=>{
    const m=JSON.parse(event.data),p=pending.get(m.id);
    if(!p)return;
    if(m.error)p.fail(Error(m.error.message));else p.ok(m.result);
  });
  const {targetInfos}=await send("Target.getTargets");
  const page=targetInfos.find(x=>x.type==="page");
  assert.ok(page,"Chrome page target required");
  const {sessionId}=await send("Target.attachToTarget",
    {targetId:page.targetId,flatten:true});
  await send("Runtime.enable",{},sessionId);
  await send("Page.enable",{},sessionId);
  const evaluate=async(expression)=>{
    const r=await send("Runtime.evaluate",
      {expression,returnByValue:true,awaitPromise:true},sessionId);
    if(r.exceptionDetails)throw Error("Browser JS exception: "+
      JSON.stringify(r.exceptionDetails).slice(0,400));
    return r.result?.value;
  };
  const get=(key)=>evaluate("localStorage.getItem("+JSON.stringify(key)+")");
  const click=(root,label)=>evaluate("(() => {const container=document.querySelector("+
    JSON.stringify(root)+");if(!container)return false;"+
    "const button=Array.from(container.querySelectorAll('button')).find(x=>"+
    "x.textContent?.trim()==="+JSON.stringify(label)+");"+
    "if(!button||button.disabled)return false;button.click();return true;})()");
  await send("Page.navigate",{url:origin+"/"},sessionId);
  await waitFor("compiled Shell",()=>evaluate('Boolean(document.querySelector(".search-button"))'));
  await evaluate('document.querySelector(".search-button").click()');
  await waitFor("command results",()=>evaluate('Boolean(document.querySelector(".command-results"))'));
  assert.equal(await evaluate('(() => {const b=Array.from(document.querySelectorAll(".command-results button"))'+
    '.find(x=>x.querySelector("b")?.textContent?.trim()==="Open Build Field");'+
    'if(!b)return false;b.click();return true;})()'),true);
  await waitFor("PixelForge desk",()=>evaluate(
    'Boolean(document.querySelector(".phios-pixelforge-identity-desk"))'));
  await evaluate("localStorage.setItem("+JSON.stringify("phios.project-registry.v1")+
    ","+JSON.stringify(v1)+")");
  await evaluate("localStorage.setItem("+JSON.stringify("phios.project-registry.v2")+
    ","+JSON.stringify(v2)+")");
  assert.equal(await get("phios.project-registry.v1"),v1);
  assert.equal(await get("phios.project-registry.v2"),v2);
  assert.equal(await evaluate('document.querySelectorAll(".phios-pixelforge-identity-desk iframe").length'),0);

  async function selectFile(file){
    const {root:doc}=await send("DOM.getDocument",{depth:-1},sessionId);
    const {nodeId}=await send("DOM.querySelector",
      {nodeId:doc.nodeId,selector:"#phios-pixelforge-identity-file"},sessionId);
    assert.ok(nodeId,"R11 actual input required");
    await send("DOM.setFileInputFiles",{nodeId,files:[file]},sessionId);
  }
  await selectFile(invalid);
  await waitFor("extra grant rejected",()=>evaluate(
    'document.querySelector(".phios-pixelforge-identity-desk [role=status]")'+
    '?.textContent?.includes("unsupported fields")'));
  assert.equal(await get("phios.project-registry.v2"),v2);
  await selectFile(valid);
  await waitFor("same-text collision reviewed",()=>evaluate(
    'document.querySelector(".phios-pixelforge-review")'+
    '?.textContent?.includes("Yes, isolated by provider")'));
  assert.equal(await get("phios.project-registry.v2"),v2,"Preview must not write");
  await evaluate("window.confirm=()=>false");
  assert.equal(await click(".phios-pixelforge-identity-desk",
    "Confirm PixelForge identity-only import"),true);
  assert.equal(await get("phios.project-registry.v2"),v2,"Canceled import wrote V2");
  await evaluate("window.confirm=()=>true");
  assert.equal(await click(".phios-pixelforge-identity-desk",
    "Confirm PixelForge identity-only import"),true);
  const mixedRaw=await waitFor("confirmed mixed V2",async()=>{
    const s=await get("phios.project-registry.v2");return s!==v2&&s;
  });
  const mixed=JSON.parse(mixedRaw);
  assert.deepEqual(mixed.entries.map(e=>[e.providerAppId,e.projectRef]),[
    ["phioffice","project:same-project"],["pixelforge","project:same-project"]]);
  assert.deepEqual(Object.keys(mixed.entries[1]),
    ["providerAppId","projectRef","title","source"]);
  assert.equal(await get("phios.project-registry.v1"),v1);
  assert.ok(!mixedRaw.includes('"execution_authority"'));
  assert.equal(await click(".phios-pixelforge-identity-desk",
    "Inspect saved PixelForge V2 IDs"),true);
  await waitFor("saved identity",()=>evaluate(
    'document.querySelector("[aria-label=\\"Saved PixelForge identities\\"]")'+
    '?.textContent?.includes("project:same-project")'));
  assert.equal(await click(".phios-pixelforge-identity-desk",
    "Review PixelForge identity removal"),true);
  await waitFor("removal review",()=>evaluate(
    'Boolean(document.querySelector("[aria-label=\\"PixelForge V2 identity removal preview\\"]"))'));
  await evaluate("window.confirm=()=>false");
  assert.equal(await click(".phios-pixelforge-identity-desk",
    "Confirm removal of this PixelForge identity"),true);
  assert.equal(await get("phios.project-registry.v2"),mixedRaw,
    "Canceled removal must retain V2");
  await evaluate("window.confirm=()=>true");
  assert.equal(await click(".phios-pixelforge-identity-desk",
    "Confirm removal of this PixelForge identity"),true);
  await waitFor("V2 exact bytes restored",async()=>
    (await get("phios.project-registry.v2"))===v2);
  assert.equal(await get("phios.project-registry.v1"),v1);
  console.log("PHIOS_R11_RENDERED_PIXELFORGE_V2:"+JSON.stringify({
    schema:"phios.r11.rendered_pixel_v2.v0.1",
    sourceCommit:process.env.GITHUB_SHA||null,
    sameTextIdProviderIsolated:true,
    previewWrites:0,canceledImportWrites:0,canceledRemovalWrites:0,
    v1BytePreserved:true,v2ExactlyRestored:true,
    grantedAuthority:false,crossOriginBridgeTested:false,nativeInstalled:false
  }));
}finally{
  if(socket?.readyState===WebSocket.OPEN){
    try{await send("Browser.close");}catch{}socket.close();
  }
  if(child?.exitCode===null)child.kill("SIGTERM");
  await new Promise(ok=>server.close(ok));
  await rm(tmp,{recursive:true,force:true,maxRetries:4,retryDelay:100});
}
