#!/usr/bin/env node
// PhiOS v0.62: evidence for reviewed, local-only UI actions and HTTP reload.
// Not an offline-device, provider, execution-grant, or installation test.
import {createRequire} from "node:module";
import {writeFile} from "node:fs/promises";
import {resolve,join} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import {options,installedRoot,loopbackServer,classifyStartupRequest} from "./offline_web_smoke.mjs";

export const REVIEWED_INTERACTIONS=Object.freeze({
  "vessie-web":Object.freeze(["atlas-navigation","atlas-filter","receipt-invalid-local","local-http-reload"]),
  "thinktank-web":Object.freeze(["audit-mode-local","local-http-reload"])
});
export function plan(app) {
  if (!Object.hasOwn(REVIEWED_INTERACTIONS,app)) throw Error("INTERACTION_UNREVIEWED_APP");
  return [...REVIEWED_INTERACTIONS[app]];
}
export function allowedProbe(raw,origin,method="GET") {
  // This is a *denied but recorded* dependency, not backend verification.
  return classifyStartupRequest(raw,origin,method)==="blocked-local-status-probe";
}
function ensure(value,code) {
  if (!value) throw Error("INTERACTION_"+code);
}
function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}
async function rendered(page) {
  await page.waitForFunction(()=>{
    const el=document.querySelector("#root");
    return !!el && el.children.length>0 && (el.innerText||"").trim().length>=24;
  },null,{timeout:15000});
  const text=await page.locator("#root").innerText();
  ensure(text.trim().length>=24,"ROOT_BLANK");
  return {chars:text.trim().length,text_sha256:digest(text.trim().slice(0,2048))};
}
async function vessie(page) {
  const steps=[];
  await page.locator(".sidebar nav button").filter({hasText:"GA108 ATLAS"}).click({timeout:10000});
  await page.locator('input[placeholder="Identity, domain, lineage..."]').waitFor();
  steps.push("atlas-navigation");
  const field=page.locator('input[placeholder="Identity, domain, lineage..."]');
  await field.fill("__PHIOS_V062_NO_MATCH__");
  await page.waitForFunction(()=>document.querySelector(".resultCount")?.textContent?.trim()==="0 / 108");
  await field.fill("");
  await page.waitForFunction(()=>document.querySelector(".resultCount")?.textContent?.trim()==="108 / 108");
  steps.push("atlas-filter");
  await page.locator(".sidebar nav button").filter({hasText:"RECEIPT INSPECTOR"}).click();
  await page.locator("#receipt-input").fill("{invalid");
  await page.locator(".inspectActions .primaryButton").click();
  await page.locator('[role="alert"].error').waitFor({timeout:10000});
  steps.push("receipt-invalid-local");
  return steps;
}
async function thinktank(page) {
  const steps=[];
  const nav=page.locator('nav[aria-label="Collaboration mode"]');
  const audit=nav.getByRole("button",{name:"AUDIT",exact:true});
  await audit.click({timeout:10000});
  await page.waitForFunction(()=>{
    const nav=document.querySelector('nav[aria-label="Collaboration mode"]');
    return [...(nav?.querySelectorAll("button")||[])].some(x=>
      x.textContent?.trim()==="AUDIT" && x.classList.contains("active"));
  });
  steps.push("audit-mode-local");
  return steps;
}

async function probe(args) {
  const app=args["--app"];
  const reviewed=plan(app);
  const root=await installedRoot(args["--trellis-home"],app);
  const requireDriver=createRequire(join(resolve(args["--playwright-root"]),"package.json"));
  const {chromium}=requireDriver("playwright-core");
  const {server,origin}=await loopbackServer(root);
  const outside=[],blockedStatus=[],websockets=[],assetFailures=[],uncaught=[];
  let browser;
  try {
    browser=await chromium.launch({executablePath:resolve(args["--chrome"]),headless:true,
      args:["--no-sandbox","--disable-background-networking","--disable-extensions",
        "--no-first-run","--no-default-browser-check"]});
    const context=await browser.newContext({serviceWorkers:"block",permissions:[],
      acceptDownloads:false,viewport:{width:1280,height:800}});
    await context.route("**/*",async route=>{
      const url=route.request().url();
      const kind=classifyStartupRequest(url,origin,route.request().method());
      if (kind==="static") await route.continue();
      else if (kind==="blocked-local-status-probe") {
        blockedStatus.push(url);
        await route.abort("blockedbyclient");
      } else {
        outside.push(url);
        await route.abort("blockedbyclient");
      }
    });
    await context.routeWebSocket("**/*",socket=>{
      websockets.push(socket.url());socket.close();
    });
    const page=await context.newPage();
    page.on("pageerror",e=>uncaught.push(String(e.message)));
    page.on("response",response=>{
      if (response.url().startsWith(origin+"/") && response.status()>=400)
        assetFailures.push(response.status()+" "+response.url());
    });
    const initial=await page.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:30000});
    ensure(initial?.status()===200,"INITIAL_DOCUMENT");
    const first=await rendered(page);
    const steps=app==="vessie-web" ? await vessie(page) : await thinktank(page);
    ensure(steps.length===reviewed.length-1,"MISSING_INTERACTION_STEP");
    ensure(steps.every((s,i)=>s===reviewed[i]),"INTERACTION_ORDER");
    // Local HTTP server stays live. This is a reload smoke, NOT loss of connectivity.
    const response=await page.reload({waitUntil:"domcontentloaded",timeout:30000});
    ensure(response?.status()===200,"RELOAD_DOCUMENT");
    const reloaded=await rendered(page);
    if (app==="vessie-web") {
      ensure((await page.locator(".main h1").innerText()).includes("Vessie"),
        "VESSIE_INITIAL_VIEW_NOT_RESTORED");
      ensure(await page.locator("#receipt-input").count()===0,
        "VESSIE_VIEW_PERSISTED");
    } else {
      const current=await page.locator('nav[aria-label="Collaboration mode"] button.active').innerText();
      ensure(current.trim()==="COUNCIL","THINKTANK_INITIAL_MODE_NOT_RESTORED");
    }
    steps.push("local-http-reload");
    await page.waitForTimeout(900);
    ensure(outside.length===0,"EXTERNAL_REQUEST");
    ensure(websockets.length===0,"WEBSOCKET_ATTEMPT");
    ensure(assetFailures.length===0,"ASSET_FAILURE");
    ensure(uncaught.length===0,"UNCAUGHT_ERROR");
    await context.close();
    return {schema:"phios.trellis_browser_interaction.v0.1",app,status:"PASS",
      browser_version:browser.version(),completed_steps:steps,
      before: first,after_reload:reloaded,external_requests:outside,
      denied_local_provider_status_probes:blockedStatus,
      websocket_attempts:websockets,local_asset_failures:assetFailures,
      uncaught_errors:uncaught,connection_profile:"127.0.0.1 HTTP available throughout",
      service_workers:"blocked",physical_offline_verified:false,
      offline_reload_verified:false,backend_verified:false,
      phios_install_authorized:false,phios_launch_authorized:false,
      external_done:false};
  } finally {
    if(browser)await browser.close();
    await new Promise(done=>server.close(done));
  }
}
async function main() {
  const o=options(process.argv.slice(2));
  let report;
  try{report=await probe(o);}catch(e) {
    report={schema:"phios.trellis_browser_interaction.v0.1",app:o["--app"],
      status:"FAIL",issues:[String(e?.message||e)],physical_offline_verified:false,
      offline_reload_verified:false,backend_verified:false,
      phios_install_authorized:false,phios_launch_authorized:false,external_done:false};
  }
  await writeFile(resolve(o["--report"]),JSON.stringify(report,null,2)+"\n",{flag:"wx"});
  console.log(JSON.stringify(report));
  if(report.status!=="PASS")process.exitCode=1;
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(e=>{console.error(e);process.exitCode=1;});
}
