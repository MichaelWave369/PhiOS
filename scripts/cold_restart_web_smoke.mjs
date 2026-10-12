#!/usr/bin/env node
// v0.64: close Chromium, kill the shell server, then start an entirely new
// Chromium process using a previously warmed persistent browser profile.
// This is controlled browser network emulation, not an air-gapped OS boot.
import {createRequire} from "node:module";
import {mkdtemp,rm,writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import {offlineRoot,expectedOfflineAction} from "./disconnected_web_smoke.mjs";
import {options,loopbackServer,classifyStartupRequest} from "./offline_web_smoke.mjs";

const PREFIX="phios-v063-readonly-v1-";
const FLAGS=["--no-sandbox","--disable-background-networking","--disable-extensions",
  "--no-first-run","--no-default-browser-check"];
const digest=s=>createHash("sha256").update(s).digest("hex");

function requireEvidence(ok,reason) {
  if(!ok)throw Error("COLD_RESTART_"+reason);
}
export function reviewedAction(app) {
  return expectedOfflineAction(app); // fixed v0.63 no-provider Atlas/AUDIT actions
}
export function networkPolicy(url,staticOrigin,method="GET") {
  const kind=classifyStartupRequest(url,staticOrigin,method);
  return kind==="static" ? "static" : kind==="blocked-local-status-probe"
    ? "denied-local-health" : "denied-other";
}
async function textReceipt(page) {
  await page.waitForFunction(()=>{
    const el=document.querySelector("#root");
    return !!el && el.children.length>0 && (el.innerText||"").trim().length>24;
  },null,{timeout:18000});
  const text=(await page.locator("#root").innerText()).trim();
  return {chars:text.length,sha256:digest(text.slice(0,2048))};
}
async function cacheEvidence(page) {
  return page.evaluate(async prefix=>{
    const keys=(await caches.keys()).filter(k=>k.startsWith(prefix));
    if(keys.length!==1)return {matching_caches:keys.length,entries:0};
    const cache=await caches.open(keys[0]);
    return {matching_caches:keys.length,entries:(await cache.keys()).length};
  },PREFIX);
}
async function instrument(context,origin,evidence) {
  await context.route("**/*",async route=>{
    const url=route.request().url();
    const policy=networkPolicy(url,origin,route.request().method());
    if(policy==="static")await route.continue();
    else {
      if(policy==="denied-local-health")evidence.localHealth.push(url);
      else evidence.external.push(url);
      await route.abort("blockedbyclient");
    }
  });
  await context.routeWebSocket("**/*",socket=>{
    evidence.ws.push(socket.url());socket.close();
  });
}
function observe(page,origin,evidence) {
  page.on("pageerror",e=>evidence.errors.push(String(e.message)));
  page.on("request",request=>{
    const url=request.url();
    const kind=networkPolicy(url,origin,request.method());
    // SW requests sometimes bypass browser route interceptors.
    if(kind==="denied-other"&&!evidence.external.includes(url))
      evidence.external.push(url);
  });
  page.on("response",response=>{
    if(response.url().startsWith(origin+"/")&&response.status()>=400)
      evidence.assets.push(response.status()+" "+response.url());
  });
}
async function awaitReady(page) {
  await page.waitForFunction(()=>!!navigator.serviceWorker?.controller,null,{timeout:20000});
  await page.evaluate(()=>navigator.serviceWorker.ready);
  const cache=await cacheEvidence(page);
  requireEvidence(cache.matching_caches===1&&cache.entries>=4,"PRECACHE_MISSING");
  requireEvidence(!await page.evaluate(()=>window.__PHIOS_OFFLINE_SW_ERROR__||null),
    "SW_BOOTSTRAP_FAILED");
  return cache;
}
async function localInteraction(page,app) {
  if(app==="vessie-web"){
    await page.locator(".sidebar nav button").filter({hasText:"GA108 ATLAS"}).click();
    const search=page.locator('input[placeholder="Identity, domain, lineage..."]');
    await search.fill("__PHIOS_COLD_RESTART_ZERO__");
    await page.waitForFunction(()=>document.querySelector(".resultCount")?.textContent?.trim()==="0 / 108");
    await search.fill("");
    await page.waitForFunction(()=>document.querySelector(".resultCount")?.textContent?.trim()==="108 / 108");
  } else {
    await page.locator('nav[aria-label="Collaboration mode"]').getByRole("button",{name:"AUDIT",exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('nav[aria-label="Collaboration mode"] button')]
      .some(el=>el.textContent?.trim()==="AUDIT"&&el.classList.contains("active")));
  }
  return reviewedAction(app);
}
async function launch(chromium,chrome,profileDir) {
  return chromium.launchPersistentContext(profileDir,{
    executablePath:resolve(chrome),headless:true,args:FLAGS,
    serviceWorkers:"allow",permissions:[],acceptDownloads:false,
    viewport:{width:1280,height:800}
  });
}
export async function check(args) {
  const app=args["--app"];
  reviewedAction(app);
  const installed=await offlineRoot(args["--trellis-home"],app);
  const requireDriver=createRequire(join(resolve(args["--playwright-root"]),"package.json"));
  const {chromium}=requireDriver("playwright-core");
  const temporary=await mkdtemp(join(tmpdir(),"phios-cold-v064-"));
  const warmProfile=join(temporary,"warm"),cleanProfile=join(temporary,"never-warmed");
  const evidence={external:[],localHealth:[],ws:[],assets:[],errors:[]};
  let server,origin,warm,cold,negative,serverClosed=false;
  try {
    const serving=await loopbackServer(installed);
    server=serving.server;origin=serving.origin;
    // Process A: online first install, with service worker and cached contents.
    warm=await launch(chromium,args["--chrome"],warmProfile);
    await instrument(warm,origin,evidence);
    const warmPage=await warm.newPage();
    observe(warmPage,origin,evidence);
    const response=await warmPage.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:30000});
    requireEvidence(response?.status()===200,"WARM_HTTP_NOT_200");
    const before=await textReceipt(warmPage);
    const cacheBefore=await awaitReady(warmPage);
    await warm.close();warm=null; // Browser process A has exited.
    await new Promise((yes,no)=>server.close(e=>e?no(e):yes()));
    serverClosed=true;

    // Process B: launch without the server and set network offline before any
    // first-party navigation, preserving only the browser profile on disk.
    cold=await launch(chromium,args["--chrome"],warmProfile);
    await cold.setOffline(true);
    await instrument(cold,origin,evidence);
    const page=await cold.newPage();
    observe(page,origin,evidence);
    const loaded=await page.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:30000});
    requireEvidence(loaded?.status()===200,"COLD_DOCUMENT_NOT_200");
    requireEvidence(loaded.fromServiceWorker(),"NOT_SERVED_BY_PERSISTED_SW");
    const after=await textReceipt(page);
    requireEvidence(before.sha256===after.sha256 && before.chars===after.chars,"COLD_DOM_DRIFT");
    const cacheAfter=await cacheEvidence(page);
    requireEvidence(cacheAfter.matching_caches===1&&cacheAfter.entries===cacheBefore.entries,
      "COLD_CACHE_DRIFT");
    const action=await localInteraction(page,app);
    await page.waitForTimeout(300);
    await cold.close();cold=null;

    // Negative control: a genuinely fresh profile must NOT cold-start while
    // server is absent and browser networking is disabled.
    negative=await launch(chromium,args["--chrome"],cleanProfile);
    await negative.setOffline(true);
    await instrument(negative,origin,evidence);
    const missing=await negative.newPage();
    observe(missing,origin,evidence);
    let unexpectedlyLoaded=false;
    try{
      const unexpected=await missing.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:7000});
      unexpectedlyLoaded=unexpected?.status()===200;
    }catch { /* Expected: no SW, no cached document, no reachable server. */ }
    requireEvidence(!unexpectedlyLoaded,"UNWARMED_PROFILE_LOADED");
    requireEvidence(await missing.locator("#root").count()===0,"UNWARMED_PROFILE_MOUNTED");
    await negative.close();negative=null;
    requireEvidence(evidence.external.length===0,"UNREVIEWED_EGRESS");
    requireEvidence(evidence.ws.length===0,"WEBSOCKET_ATTEMPT");
    requireEvidence(evidence.assets.length===0,"BROKEN_STATIC_ASSETS");
    requireEvidence(evidence.errors.length===0,"PAGE_ERRORS");
    return {schema:"phios.trellis_browser_cold_restart.v0.1",app,status:"PASS",
      launched_two_distinct_browser_processes:true,http_server_stopped_before_restart:true,
      network_emulation_offline_before_navigation:true,
      document_from_persisted_service_worker:true,
      fresh_unwarmed_profile_cold_start_refused:true,
      warm_cached_files:cacheBefore.entries,restarted_cached_files:cacheAfter.entries,
      before,after,local_only_interaction:action,
      unexpected_requests:evidence.external,denied_local_health_probes:evidence.localHealth,
      websockets:evidence.ws,asset_errors:evidence.assets,page_errors:evidence.errors,
      physical_airgap_verified:false,phios_boot_verified:false,
      backend_or_model_execution_verified:false,reproducible_dependency_closure:false,
      phios_install_authorized:false,phios_launch_authorized:false,external_done:false};
  }finally {
    for(const browser of [negative,cold,warm])if(browser)await browser.close().catch(()=>{});
    if(server&&!serverClosed)await new Promise(done=>server.close(done));
    await rm(temporary,{recursive:true,force:true});
  }
}
async function main() {
  const args=options(process.argv.slice(2));
  let report;
  try{report=await check(args);}
  catch(e){report={schema:"phios.trellis_browser_cold_restart.v0.1",
    app:args["--app"],status:"FAIL",issues:[String(e?.message||e)],
    physical_airgap_verified:false,phios_boot_verified:false,
    backend_or_model_execution_verified:false,phios_install_authorized:false,
    phios_launch_authorized:false,external_done:false};}
  await writeFile(resolve(args["--report"]),JSON.stringify(report,null,2)+"\n",{flag:"wx"});
  console.log(JSON.stringify(report));
  if(report.status!=="PASS")process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  main().catch(e=>{console.error(e);process.exitCode=1;});
}
