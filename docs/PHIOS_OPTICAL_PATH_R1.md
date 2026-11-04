# PhiOS Optical Path R1: offline opto-electrical link-budget advisor

**Status:** Opt-in, read-only, wholly synthetic cost model. Does not inspect devices, transmit a packet, open a socket, install drivers, route traffic, load AI weights, control motors, or affect kernel/power/performance settings.

## Why

A useful response to the question "why not replace all copper with fiber?" requires quantifying **conversion, endpoint idle power, serialization, startup, reliability and thermal overhead**, rather than assuming light is automatically cheaper or faster. Short copper traces can beat optical links because the optical conversion path itself costs time, energy, board area and heat; optical solutions can be attractive over longer distances or demanding aggregate bandwidth once measured and engineered.

This experiment is separate from the existing PhiOS Elastic Runtime and GPU Observatory, and cannot grant their permissions.

## Scientific distinction

- [Kalra et al. 2023](https://doi.org/10.1021/acscentsci.2c01114) measured excited-state migration in microtubules.
- [Babcock et al. 2024](https://doi.org/10.1021/acs.jpcb.3c07936) predicted and investigated collective ultraviolet emission from biological tryptophan networks.
- Those are **not** empirical evidence about modern silicon photonics link latency, BER or transceiver power, and do **not** establish consciousness. See [Altermath's parallel toy models](https://github.com/MichaelWave369/Altermath/blob/main/docs/bio-lattice-research.md).

## R1 model

Each path declares:
- bandwidth in **Gbit/s**;
- fixed base latency and extra conversion time in **microseconds**;
- average assumed active endpoint overhead power in **watts** (called `idle_power_w` in the API);
- marginal transmission energy in **pJ/bit**;
- setup energy in **microjoules**.

For each byte payload, compute:

`serialization_seconds = 8 * bytes / (bandwidth_gbps * 1e9)`

`time_seconds = serialization_seconds + (base_latency_us + conversion_latency_us) / 1e6`

`energy_j = idle_power_w * time_seconds + (8*bytes) * dynamic_energy_pj_per_bit * 1e-12 + setup_energy_uj * 1e-6`

The output shows separate *synthetic latency winner* and *synthetic energy winner* for each payload. There is **no** automatic routing winner and no promise of net energy or wall-clock improvement. Endpoint power here is an assumed scalar during message service, not a full real-world idle/wake model.

**Known omissions:** buffering, clocks, optical budgets and losses, BER/FEC, packetization, protocol stack, DMA/CPU copies, transceiver wake and laser safety, interference, concurrency, thermal derating, passive fiber bend limits, manufacturing, cost and fan/thermal control.

## Run locally (no network or device access)

```sh
python -m phios.optical_path_r1 --sizes 64,4096,65536,1048576
python -m phios.optical_path_r1 --sizes 64,4096,65536 --optical-conversion-us 1.5 --optical-idle-w 3.0
python -m pytest -q tests/test_optical_path_r1.py
```

The tool prints deterministic JSON with schema `phios.optical-path-study.v1`, `evidence_class: illustrative_synthetic_unmeasured`, `hardware_access: false`, `automatic_routing: false` and `authority: advisory_only`. Defaults are invented to explore tradeoffs. **Do not circulate their numerical values as hardware specifications.**

## Future measurement gates

1. Match **actual**, published, independently checked components: copper serializer/deserializer and optical E/O and O/E links with comparable payload, distance, bit error target, host interface, thermal conditions, and real total endpoint idle/active power.
2. Record packet sizes, latency histograms (p50/p95/p99), bandwidth under concurrent load, energy-per-payload measured at the electrical input, BER, recovery time and total thermal dissipation.
3. Replicate with isolated noncritical equipment and fault injection, including disconnected fiber, stale buffers, transceiver power loss, congestion, clock/FEC and temperature. Report negative results.
4. Integrate only **advisory results** into an opt-in PhiOS observatory. Any real data-path changes require a separate human-reviewed architecture and verified fallback.
5. PHB/JOYVEIN data paths may be future consumers. The PHB Reflex/SAFE–ARM physical authority path must remain independent of this experimental optical transport.

## Test invariants

- Input validation rejects nonfinite, negative, oversized or malformed synthetic parameters.
- Results are deterministic; nan/inf never appear in emitted JSON.
- A short payload retains the optical conversion penalty; a larger payload exposes possible throughput advantage.
- No subprocess, hardware, network or actual kernel changes are needed during normal API/CLI operation.
