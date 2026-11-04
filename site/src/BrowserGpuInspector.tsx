import { useState } from "react";

type AdapterSummary = { vendor?: string; architecture?: string; features?: ReadonlySet<string> };
type GpuProvider = { requestAdapter: () => Promise<{ info?: AdapterSummary; features?: ReadonlySet<string> } | null> };
type ProbeStatus = "idle" | "checking" | "available" | "unavailable" | "error";

export default function BrowserGpuInspector() {
  const [status, setStatus] = useState<ProbeStatus>("idle");
  const [details, setDetails] = useState<{ vendor: string; architecture: string; featureCount: number } | null>(null);

  async function inspect() {
    setStatus("checking");
    setDetails(null);
    const gpu = (navigator as Navigator & { gpu?: GpuProvider }).gpu;
    if (!gpu || !window.isSecureContext) {
      setStatus("unavailable");
      return;
    }
    try {
      const adapter = await gpu.requestAdapter();
      if (!adapter) { setStatus("unavailable"); return; }
      setDetails({
        vendor: adapter.info?.vendor || "Not exposed",
        architecture: adapter.info?.architecture || "Not exposed",
        featureCount: adapter.features?.size ?? 0,
      });
      setStatus("available");
    } catch {
      setStatus("error");
    }
  }

  return (
    <section className="gpu-inspector" id="gpu-observatory" aria-labelledby="gpu-title">
      <span className="kicker">Φ GPU OBSERVATORY / WEB</span>
      <h2 id="gpu-title">Measure what this browser can actually see.</h2>
      <p>Optional local WebGPU adapter inspection. No automatic hardware probing, no uploads,
      no performance claims, and no GPU unlocking. Browser access does not reveal CUDA,
      physical VRAM, Tensor throughput, clocks, or the true rendering bottleneck.</p>
      <button type="button" onClick={() => { void inspect(); }} disabled={status === "checking"}>
        {status === "checking" ? "Inspecting locally…" : "Inspect browser GPU capability"}
      </button>
      <p role="status" aria-live="polite">
        {status === "idle" && "Not inspected. Your choice."}
        {status === "checking" && "Requesting a browser GPU adapter…"}
        {status === "unavailable" && "WebGPU adapter unavailable or not permitted in this browser/context."}
        {status === "error" && "Inspection failed; no GPU capability is assumed."}
        {status === "available" && "WebGPU adapter available. This is not a CUDA benchmark."}
      </p>
      {details && <dl>
        <dt>Reported vendor</dt><dd>{details.vendor}</dd>
        <dt>Reported architecture</dt><dd>{details.architecture}</dd>
        <dt>Available WebGPU features</dt><dd>{details.featureCount} (count only)</dd>
      </dl>}
      <p><a href="https://github.com/MichaelWave369/PhiOS/blob/main/docs/PHIOS_GPU_OBSERVATORY_V01.md">
        Read GPU Observatory scope and local CLI →</a></p>
    </section>
  );
}
