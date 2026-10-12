#!/usr/bin/env node
// v0.63: a real disconnected browser reload from a separately packaged,
// first-party SW cache. No PhiOS installer, desktop or model authority.
import {createRequire} from "node:module";
import {lstat,realpath,writeFile} from "node:fs/promises";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import {loopbackServer,classifyStartupRequest,options} from "./offline_web_smoke.mjs";

const APPROVED=new Set(["vessie-web","thinktank-web"]);
export async function offlineRoot(home,app) {
  if(!APPROVED.has(app))throw Error("DISCONNECTED_UNREVIEWED_APP");
  const h=resolve(home),hs=await lstat(h);
  if(!hs.isDirectory()||hs.isSymbolicLink())throw Error("DISCONNECTED_HOME_INVALID");
  const dir=join(h,"cellar","phios-"+app+"-offline","0.1.0");
  const st=await lstat(dir);
  if(!st.isDirectory()||st.isSymbolicLink()||await realpath(dir)!==dir)
    throw Error("DISCONNECTED_INSTALLED_DIR_INVALID");
  for(const name of ["index.html","phios-offline-sw.js","phios-offline-bootstrap.js"]) {
    const file=join(dir,name),s=await lstat(file);
    if(!s.isFile()||s.isSymbolicLink())throw Error("DISCONNECTED_ASSET_INVALID");
  }
  return dir;
}
export function expectedOfflineAction(app) {
  if(!APPROVED.has(app))throw Error("DISCONNECTED_UNREVIEWED_APP");
  return app==="vessie-web"?"atlas-filter":"audit-mode";
}
const hash=value=>createHash("sha256").update(value).digest("hex");
function ensure(value,code){if(!value)throw Error("DISCONNECTED_"+code);}
async function mounted(page){
  await page.waitForFunction(()=>{
    const root=document.querySelector("#root");
    return root?.children.length>0 && (root.innerText||"").trim().length>=24;
  },null,{timeout:20000});
  const t=(await page.locator("#root").innerText()).trim();
  return {visible_chars:t.length,visible_sha256:hash(t.slice(0,2048))};
}
async function interact(page,app){
  if(app==="vessie-web"){
    await page.locator(".sidebar nav button").filter({hasText:"GA108 ATLAS"}).click({timeout:10000});
    const search=page.locator('input[placeholder="Identity, domain, lineage..."]');
    await search.fill("__PHIOS_DISCONNECTED_NONE__");
    await page.waitForFunction(()=>document.querySelector(".resultCount")?.textContent?.trim()==="0 / 108");
    await search.fill("");
    await page.waitForFunction(()=>document.querySelector(".resultCount")?.textContent?.trim()==="108 / 108");
  }else{
    const audit=page.locator('nav[aria-label="Collaboration mode"]').getByRole("button",{name:"AUDIT",exact:true});
    await audit.click({timeout:10000});
    await page.waitForFunction(()=>[...document.querySelectorAll('nav[aria-label="Collaboration mode"] button')].some(
      node=>node.textContent?.trim()==="AUDIT"&&node.classList.contains("active")));
  }
  return expectedOfflineAction(app);
}
async function run(args) {
  const app=args["--app"];
  const root=await offlineRoot(args["--trellis-home"],app);
  const driver=createRequire(join(resolve(args["--playwright-root"]),"package.json"));
  const {chromium}=driver("playwright-core");
  let running=await loopbackServer(root);
  const origin=running.origin;
  let closed=false,browser;
  const external=[],blockedProbes=[],ws=[],assetErrors=[],pageErrors=[];
  try{
    browser=await chromium.launch({executablePath:resolve(args["--chrome"]),headless:true,
      args:["--no-sandbox","--disable-background-networking","--disable-extensions",
        "--no-first-run","--no-default-browser-check"]});
    const context=await browser.newContext({serviceWorkers:"allow",permissions:[],
      acceptDownloads:false,viewport:{width:1280,height:800}});
    await context.route("**/*",async route=>{
      const url=route.request().url();
      const kind=classifyStartupRequest(url,origin,route.request().method());
      if(kind==="static")await route.continue();
      else if(kind==="blocked-local-status-probe"){
        blockedProbes.push(url);await route.abort("blockedbyclient");
      }else{external.push(url);await route.abort("blockedbyclient");}
    });
    await context.routeWebSocket("**/*",socket=>{ws.push(socket.url());socket.close();});
    const page=await context.newPage();
    page.on("pageerror",e=>pageErrors.push(String(e.message)));
    page.on("request",request=>{
      const url=request.url();
      const kind=classifyStartupRequest(url,origin,request.method());
      // Also observe SW-controlled requests that might bypass Playwright routing.
      if(kind==="external"&&!external.includes(url))external.push(url);
    });
    page.on("response",response=>{
      if(response.url().startsWith(origin+"/")&&response.status()>=400)
        assetErrors.push(response.url()+" "+response.status());
    });
    const first=await page.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:30000});
    ensure(first?.status()===200,"INITIAL_HTTP_DOCUMENT");
    const before=await mounted(page);
    await page.waitForFunction(()=>!!navigator.serviceWorker?.controller,null,{timeout:20000});
    const cacheBefore=await page.evaluate(async()=>{
      const keys=(await caches.keys()).filter(x=>x.startsWith("phios-v063-readonly-v1-"));
      if(keys.length!==1)return {count:keys.length,entries:0};
      const cache=await caches.open(keys[0]);
      return {count:keys.length,entries:(await cache.keys()).length};
    });
    ensure(cacheBefore.count===1&&cacheBefore.entries>=3,"PRECACHE_INCOMPLETE");
    ensure(!(await page.evaluate(()=>window.__PHIOS_OFFLINE_SW_ERROR__||null)),
      "SERVICE_WORKER_BOOTSTRAP_ERROR");
    // Close the only actual HTTP server, then tell Chromium to go offline.
    await new Promise((done,fail)=>running.server.close(e=>e?fail(e):done()));
    closed=true;
    await context.setOffline(true);
    const response=await page.reload({waitUntil:"domcontentloaded",timeout:30000});
    ensure(response?.status()===200,"DISCONNECTED_DOCUMENT_FAILED");
    ensure(response.fromServiceWorker(),"NOT_FROM_SERVICE_WORKER");
    const after=await mounted(page);
    ensure(after.visible_chars===before.visible_chars &&
      after.visible_sha256===before.visible_sha256,"RELOAD_UI_DRIFT");
    const action=await interact(page,app);
    await page.waitForTimeout(700);
    ensure(external.length===0,"UNREVIEWED_EGRESS_ATTEMPT");
    ensure(ws.length===0,"WEBSOCKET_ATTEMPT");
    ensure(assetErrors.length===0,"ASSET_FAILURE");
    ensure(pageErrors.length===0,"UNCAUGHT_JAVASCRIPT");
    await context.close();
    return {schema:"phios.trellis_disconnected_reload.v0.1",app,status:"PASS",
      browser_version:browser.version(),disconnected_http_server:true,
      chromium_network_offline:true,document_from_service_worker:true,
      precached_assets:cacheBefore.entries,before,after,
      safe_offline_action:action,unexpected_requests:external,
      denied_local_provider_status_probes:blockedProbes,
      websocket_attempts:ws,missing_static_files:assetErrors,
      uncaught_errors:pageErrors,phios_desktop_boot_verified:false,
      airgapped_machine_verified:false,provider_models_verified:false,
      phios_install_authorized:false,phios_launch_authorized:false,
      external_done:false};
  }finally{
    if(browser)await browser.close();
    if(!closed)await new Promise(done=>running.server.close(done));
  }
}
async function main(){
  const args=options(process.argv.slice(2));
  let result;
  try{result=await run(args);}
  catch(e){result={schema:"phios.trellis_disconnected_reload.v0.1",app:args["--app"],
    status:"FAIL",issues:[String(e?.message||e)],phios_desktop_boot_verified:false,
    airgapped_machine_verified:false,provider_models_verified:false,
    phios_install_authorized:false,phios_launch_authorized:false,external_done:false};}
  await writeFile(resolve(args["--report"]),JSON.stringify(result,null,2)+"\n",{flag:"wx"});
  console.log(JSON.stringify(result));
  if(result.status!=="PASS")process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  main().catch(e=>{console.error(e);process.exitCode=1;});
}
