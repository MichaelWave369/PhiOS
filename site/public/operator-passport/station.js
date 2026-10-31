import { createPortablePassportStore, parsePortablePassport } from "./sdk.js";
const $ = id => document.getElementById(id);
let storage = null;
try { storage = localStorage; } catch { /* blocked browser storage */ }
const operator = createPortablePassportStore({ storage });
function render() {
  const summary = operator.snapshot();
  document.body.classList.toggle("operator-grid", operator.hasBenefit("phios-site-grid"));
  const architect = operator.hasBenefit("phios-architect-mark");
  $("mark").textContent = architect ? "Φ369" : "Φ";
  $("dossier-title").textContent = summary.imported
    ? "STANDARD RANK " + summary.clearedRank + " / 6" : "NO PASSPORT IMPORTED";
  $("benefits").textContent = !summary.imported
    ? "Every page and capability represented here remains available without a Passport."
    : architect ? "Φ369 Architect seal earned. This is a cosmetic honor, not a security credential."
      : operator.hasBenefit("phios-site-grid")
        ? "The decorative Field Grid is active. Your actual system permissions remain unchanged."
        : "Your Passport is here. Reach Standard Rank 3 to reveal the Field Grid.";
  $("passport-export").disabled = !summary.imported;
  $("passport-remove").disabled = !summary.imported;
}
$("passport-file").addEventListener("change", async event => {
  const file = event.currentTarget.files?.[0];
  event.currentTarget.value = "";
  if (!file) return;
  try {
    if (file.size > 16384) throw new TypeError("File exceeds the 16 KiB limit.");
    const text = await file.text();
    const valid = parsePortablePassport(text);
    const recorded = valid.results.filter(r => r.mode === "standard").length;
    if (!confirm("Import " + recorded + " recorded Standard result(s)? This replaces only the local Passport copy used on this public site.")) return;
    const result = operator.importJSON(text);
    render();
    $("message").textContent = result.persisted
      ? "Passport imported locally. Cosmetic rewards updated."
      : "Passport loaded for this session. Browser storage is unavailable, so export a backup.";
  } catch (error) {
    $("message").textContent = "Import rejected: " + error.message;
  }
});
$("passport-export").addEventListener("click", () => {
  const content = operator.exportJSON();
  if (!content) return;
  const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
  const a = document.createElement("a");
  a.download = "phioperator-passport-v1.json";
  a.href = url;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("message").textContent = "Local Passport copy exported.";
});
$("passport-remove").addEventListener("click", () => {
  if (!operator.snapshot().imported || !confirm("Remove the imported Passport from this PhiOS website?")) return;
  operator.clear();
  render();
  $("message").textContent = "Passport removed here. No PhiOS systems or other sites were changed.";
});
render();