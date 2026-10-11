#!/usr/bin/env node
// PhiOS v0.61: disposable Trellis-installed React startup evidence.
// Not a PhiOS app installation, launch authorization, or full offline certification.
import {createServer} from "node:http";
import {readFile, lstat, realpath, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {resolve, relative, join, extname, isAbsolute, sep} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";

const APPS = new Set(["vessie-web", "thinktank-web"]);
const TYPES = {".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8",
  ".css":"text/css; charset=utf-8", ".json":"application/json; charset=utf-8",
  ".svg":"image/svg+xml", ".png":"image/png", ".jpg":"image/jpeg",
  ".ico":"image/x-icon", ".woff2":"font/woff2", ".webp":"image/webp"};

export function options(args) {
  const result = {};
  for (let i=0; i<args.length; i+=2) {
    if (!["--app","--trellis-home","--chrome","--playwright-root","--report"].includes(args[i])
      || !args[i+1] || result[args[i]]) throw Error("SMOKE_INVALID_ARGUMENTS");
    result[args[i]] = args[i+1];
  }
  for (const key of ["--app","--trellis-home","--chrome","--playwright-root","--report"]) {
    if (!result[key]) throw Error("SMOKE_MISSING_"+key);
  }
  if (!APPS.has(result["--app"])) throw Error("SMOKE_UNREVIEWED_APP");
  return result;
}

export function localPath(root, pathname) {
  if (typeof pathname !== "string" || !pathname.startsWith("/")) return null;
  let decoded;
  try { decoded=decodeURIComponent(pathname); } catch { return null; }
  if (decoded.includes("\\") || decoded.includes("\0") || decoded.includes("//")) return null;
  const parts=decoded.split("/").filter(Boolean);
  if (parts.some(x=>x==="." || x===".." || x.startsWith("."))) return null;
  const candidate=resolve(root,parts.length?parts.join("/"):"index.html");
  const rel=relative(resolve(root),candidate);
  return rel===".." || rel.startsWith(".."+sep) || isAbsolute(rel) ? null : candidate;
}

export async function installedRoot(home,app) {
  if (!APPS.has(app)) throw Error("SMOKE_UNREVIEWED_APP");
  home=resolve(home);
  const h=await lstat(home);
  if (!h.isDirectory() || h.isSymbolicLink()) throw Error("SMOKE_HOME_NOT_REAL");
  const root=join(home,"cellar","phios-"+app,"0.1.0");
  const st=await lstat(root);
  if (!st.isDirectory() || st.isSymbolicLink() || await realpath(root)!==root) {
    throw Error("SMOKE_INSTALLED_DIR_INVALID");
  }
  const index=await lstat(join(root,"index.html"));
  if (!index.isFile() || index.isSymbolicLink()) throw Error("SMOKE_INDEX_INVALID");
  return root;
}

export async function loopbackServer(root) {
  root=await realpath(root);
  const server=createServer(async(req,res)=>{
    try {
      if (!["GET","HEAD"].includes(req.method)) {res.writeHead(405);res.end();return;}
      const url=new URL(req.url,"http://127.0.0.1");
      const filename=localPath(root,url.pathname);
      if (!filename) {res.writeHead(403);res.end();return;}
      const st=await lstat(filename);
      if (!st.isFile() || st.isSymbolicLink() || await realpath(filename)!==filename) {
        res.writeHead(403);res.end();return;
      }
      const bytes=await readFile(filename);
      res.writeHead(200,{"content-type":TYPES[extname(filename).toLowerCase()]||"application/octet-stream",
        "cache-control":"no-store","x-content-type-options":"nosniff"});
      res.end(req.method==="HEAD"?undefined:bytes);
    } catch {if (!res.headersSent) res.writeHead(404);res.end();}
  });
  await new Promise((done,fail)=>{server.once("error",fail);server.listen(0,"127.0.0.1",done);});
  return {server,origin:"http://127.0.0.1:"+server.address().port};
}

async function probe(o) {
  const root=await installedRoot(o["--trellis-home"],o["--app"]);
  const requireInTemp=createRequire(join(resolve(o["--playwright-root"]),"package.json"));
  const {chromium}=requireInTemp("playwright-core");
  const {server,origin}=await loopbackServer(root);
  const outside=[],wsAttempts=[],missing=[],pageErrors=[];
  let browser;
  try {
    browser=await chromium.launch({executablePath:resolve(o["--chrome"]),headless:true,
      args:["--no-sandbox","--disable-background-networking","--disable-extensions",
        "--no-first-run","--no-default-browser-check"]});
    const context=await browser.newContext({serviceWorkers:"block",permissions:[],
      acceptDownloads:false,viewport:{width:1280,height:800}});
    await context.route("**/*",async route=>{
      const raw=route.request().url();
      let url;
      try {url=new URL(raw);} catch {outside.push(raw);await route.abort();return;}
      if (url.protocol==="http:" && url.origin===origin) await route.continue();
      else {outside.push(raw);await route.abort("blockedbyclient");}
    });
    await context.routeWebSocket("**/*", socket=>{wsAttempts.push(socket.url());socket.close();});
    const page=await context.newPage();
    page.on("pageerror", e=>pageErrors.push(String(e.message)));
    page.on("response",r=>{
      if (r.url().startsWith(origin+"/") && r.status()>=400) missing.push(r.status()+" "+r.url());
    });
    const response=await page.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:30000});
    if (!response || response.status()!==200) throw Error("SMOKE_ENTRY_NOT_200");
    await page.waitForFunction(()=>{
      const root=document.querySelector("#root");
      return root && root.children.length>0 && (root.innerText||"").trim().length>=24;
    },null,{timeout:15000});
    await page.waitForTimeout(1200);
    const dom=await page.evaluate(()=>{
      const root=document.querySelector("#root");
      return {chars:(root?.innerText||"").trim().length,children:root?.children.length||0,
        text:(root?.innerText||"").trim().slice(0,2000),
        scripts:performance.getEntriesByType("resource").filter(x=>x.name.includes(".js")).length};
    });
    const errors=[];
    if (dom.scripts<1) errors.push("NO_COMPILED_JS_LOADED");
    if (outside.length) errors.push("EXTERNAL_HTTP_REQUEST_ATTEMPT");
    if (wsAttempts.length) errors.push("WEBSOCKET_REQUEST_ATTEMPT");
    if (missing.length) errors.push("LOCAL_ASSET_FAILED");
    if (pageErrors.length) errors.push("UNCAUGHT_PAGE_ERROR");
    await context.close();
    return {schema:"phios.trellis_chromium_shell.v0.1",app:o["--app"],
      status:errors.length?"FAIL":"PASS",browser_version:browser.version(),
      visible_character_count:dom.chars,root_children:dom.children,js_resources:dom.scripts,
      visible_text_sha256:createHash("sha256").update(dom.text).digest("hex"),
      external_requests:outside,websocket_attempts:wsAttempts,local_asset_failures:missing,
      uncaught_errors:pageErrors,issues:errors,
      scope:"initial React shell from Trellis-installed static files via loopback-only HTTP; egress blocked",
      not_verified:["full physical-offline restart","runtime AI/provider operations",
        "reproducible npm dependency closure","PhiOS installation","desktop launch","ISO packaging"],
      phios_install_authorized:false,phios_launch_authorized:false,external_done:false};
  } finally {
    if (browser) await browser.close();
    await new Promise(done=>server.close(done));
  }
}

async function main() {
  const o=options(process.argv.slice(2));
  let report;
  try {report=await probe(o);}
  catch(e) {report={schema:"phios.trellis_chromium_shell.v0.1",app:o["--app"],status:"FAIL",
    issues:[String(e?.message||e)],phios_install_authorized:false,
    phios_launch_authorized:false,external_done:false};}
  await writeFile(resolve(o["--report"]),JSON.stringify(report,null,2)+"\n",{flag:"wx"});
  console.log(JSON.stringify(report));
  if (report.status!=="PASS") process.exitCode=1;
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(e=>{console.error(e);process.exitCode=1;});
}
