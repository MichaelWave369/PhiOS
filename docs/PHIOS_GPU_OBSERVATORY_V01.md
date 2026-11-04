# PhiOS GPU Observatory v0.1

**Scope:** read-only observations with provenance; not an NVIDIA unlocker, overclocker, device driver, or automatic optimizer.

## Architecture

- **Native PhiOS / Windows / Linux:** `phi-gpu observe` (or `python -m phios.gpu_observer observe`) invokes `nvidia-smi` with a fixed, bounded query. Returns the `phios.gpu-observation.v1` envelope. If the CLI, GPU or driver is absent, status is `unavailable`, never a fictitious zero.
- **PhiOS website / PWA / Mobile browser:** voluntary WebGPU adapter introspection only. Adapter vendor and feature availability are browser reports, not CUDA or hardware benchmark results.
- **Android native launcher:** may expose OS-reported graphics API version and memory class; no direct privileged GPU metrics, clocks, and no root.
- **XR/WebXR:** browser adapter observations must not be mistaken for Quest frame timing. Future host integrations should use explicit XR frame-time measurements, permission checks, and device-specific performance hints.
- **Legacy PhiOS V3 / MK1:** consume the same envelope when their host supplies a genuine observation; no fabricated GPU metrics.

## Local CLI

```sh
phi-gpu observe
# or without installing a console entry point:
python -m phios.gpu_observer observe
```

NVIDIA fields: name, driver, MiB capacity/used, GPU and memory-controller utilization percent, temperature, power draw and limit. All may be `null`. One snapshot is not a statistically valid bottleneck diagnosis. No logs or data are uploaded.

For an independently timed before/after comparison, create two JSON files with matching experiment keys:

```json
{
  "schema": "phios.gpu-run.v1",
  "workload": "sdxl",
  "gpu": "RTX 3060",
  "precision": "fp16",
  "batch": 1,
  "resolution": "1024x1024",
  "execution_mode": "local",
  "duration_ms": 2000
}
```

```sh
phi-gpu compare before.json after.json
```

This reports elapsed-time ratio and reduction, marked **single-pair; repeat trials required**. Keep the model revision, prompt, seeds, drivers, power cap, thermals, batch, context length, and warmup methodology fixed. Use multiple runs and median with dispersion before publishing claims.

## Bottleneck map (hypotheses, not shortcuts)

| Measurement | What it might mean | Next non-invasive check |
| --- | --- | --- |
| VRAM near capacity | Offload/allocator and OOM pressure | Reduce batch, quantize, profile transfers |
| GPU utilization high | Device active; may be compute or memory | Kernel timeline and arithmetic intensity |
| GPU utilization low | Host preparation, synchronization or I/O possible | CPU and disk traces, overlap copies |
| Fast prefill, slow decode | Token-generation bandwidth/latency bottleneck | Model size/quantization, KV cache, context |
| Poor XR frame pacing | CPU/GPU/thermal/compositor deadline issues | XR frame timestamps, GPU capture when available |

GPU architecture can cap BF16/FP16/TF32 rates independently of physical hardware, but the 2026 `gpu-unlock` reports are model-specific and **do not imply 2× application speed**. Blackwell RTX 50 remains unsupported by that project. This Observatory does not import, recommend installing, or execute a GPU unlock. Firmware, UEFI, VBIOS, driver and power changes require separate evidence and explicit operator approval outside this capability.

## Contract and security

- `authority: observe-only` for hardware read; `advisory-only` for comparisons.
- Fixed subprocess argument array with `shell=False`, four-second timeout, 16-GPU cap, 32 KiB input cap.
- No background sampling, persistence, remote transmission, or new runtime dependencies.
- Output is a local, untrusted point-in-time sample. Never equate adapter support with entitlement to change configuration.
- Next rungs: opt-in benchmark harness with latency distributions; CUDA/DirectML/Vulkan/WebGPU backend comparison; per-workload routing suggestions; explicit host adapter for XR frame-budget reporting; safe rollback plans.
