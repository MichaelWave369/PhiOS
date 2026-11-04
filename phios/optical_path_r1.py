"""PhiOS Optical Path R1: deterministic offline synthetic link-budget comparisons.

No hardware enumeration, drivers, privileged controls, networking, or actual routing.
All supplied default parameters are illustrative and are NOT measured specifications.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Sequence

SCHEMA = "phios.optical-path-study.v1"
MAX_BYTES = 1_000_000_000


@dataclass(frozen=True)
class LinkAssumptions:
    """A user-supplied or illustrative complete end-to-end link budget."""

    label: str
    bandwidth_gbps: float
    base_latency_us: float
    conversion_latency_us: float
    idle_power_w: float
    dynamic_energy_pj_per_bit: float
    setup_energy_uj: float

    def validated(self) -> "LinkAssumptions":
        ranges = {
            "bandwidth_gbps": (0.001, 10_000.0),
            "base_latency_us": (0.0, 1_000_000.0),
            "conversion_latency_us": (0.0, 1_000_000.0),
            "idle_power_w": (0.0, 100_000.0),
            "dynamic_energy_pj_per_bit": (0.0, 1_000_000.0),
            "setup_energy_uj": (0.0, 1_000_000.0),
        }
        if not self.label or len(self.label) > 60:
            raise ValueError("label must be 1-60 characters")
        for name, (minimum, maximum) in ranges.items():
            value = getattr(self, name)
            if not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if value < minimum or value > maximum:
                raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
        return self


# Invented values to expose conversion/idle-cost tradeoffs, not hardware data.
ILLUSTRATIVE_COPPER = LinkAssumptions(
    label="synthetic electrical link", bandwidth_gbps=32.0, base_latency_us=0.10,
    conversion_latency_us=0.0, idle_power_w=0.45,
    dynamic_energy_pj_per_bit=12.0, setup_energy_uj=0.08,
)
ILLUSTRATIVE_OPTICAL = LinkAssumptions(
    label="synthetic optical link", bandwidth_gbps=64.0, base_latency_us=0.25,
    conversion_latency_us=0.45, idle_power_w=1.40,
    dynamic_energy_pj_per_bit=3.5, setup_energy_uj=1.20,
)


def estimate_transfer(payload_bytes: int, spec: LinkAssumptions) -> dict:
    """Compute serial transfer plus full assumed endpoint overhead for one payload.

    Illustrative scalar accounting only. No queueing, contention, BER/FEC, retries,
    temperature, device scheduling, laser safety, or actual power sampling.
    """
    if isinstance(payload_bytes, bool) or not isinstance(payload_bytes, int):
        raise ValueError("payload_bytes must be an integer")
    if not 1 <= payload_bytes <= MAX_BYTES:
        raise ValueError(f"payload_bytes must be 1..{MAX_BYTES}")
    spec.validated()
    bits = 8 * payload_bytes
    serialization_s = bits / (spec.bandwidth_gbps * 1_000_000_000)
    overhead_s = (spec.base_latency_us + spec.conversion_latency_us) / 1_000_000
    total_time_s = overhead_s + serialization_s
    total_energy_j = (
        spec.idle_power_w * total_time_s
        + bits * spec.dynamic_energy_pj_per_bit * 1e-12
        + spec.setup_energy_uj * 1e-6
    )
    return {
        "payload_bytes": payload_bytes,
        "latency_us": total_time_s * 1_000_000,
        "energy_j": total_energy_j,
        "energy_uj": total_energy_j * 1_000_000,
        "serialization_us": serialization_s * 1_000_000,
        "fixed_overhead_us": spec.base_latency_us + spec.conversion_latency_us,
    }


def compare_paths(
    payload_sizes: Sequence[int],
    electrical: LinkAssumptions = ILLUSTRATIVE_COPPER,
    optical: LinkAssumptions = ILLUSTRATIVE_OPTICAL,
) -> dict:
    """Produce an auditable, non-authoritative table for matched packet sizes."""
    electrical.validated()
    optical.validated()
    if not 1 <= len(payload_sizes) <= 128:
        raise ValueError("Provide between 1 and 128 payload sizes")
    if not all(isinstance(size, int) and not isinstance(size, bool) for size in payload_sizes):
        raise ValueError("All sizes must be integers")
    cases = []
    for size in payload_sizes:
        copper_result = estimate_transfer(size, electrical)
        optical_result = estimate_transfer(size, optical)
        cases.append({
            "payload_bytes": size,
            "electrical": copper_result,
            "optical": optical_result,
            "latency_winner_synthetic": (
                "electrical" if copper_result["latency_us"] <= optical_result["latency_us"]
                else "optical"
            ),
            "energy_winner_synthetic": (
                "electrical" if copper_result["energy_j"] <= optical_result["energy_j"]
                else "optical"
            ),
        })
    return {
        "schema": SCHEMA,
        "evidence_class": "illustrative_synthetic_unmeasured",
        "authority": "advisory_only",
        "hardware_access": False,
        "automatic_routing": False,
        "assumptions": {"electrical": asdict(electrical), "optical": asdict(optical)},
        "cases": cases,
        "limitations": [
            "All default parameters are invented; winners are not device recommendations.",
            "Electrical and optical endpoints both require power and thermal management.",
            "No queueing, contention, BER, retries, error correction, connectors or eye safety.",
            "No motor, Reflex, kernel, driver, model-weight, or bus state is modified.",
        ],
    }


def _parse_sizes(raw: str) -> list[int]:
    parts = raw.split(",")
    if not parts or len(parts) > 128:
        raise ValueError("Expected between 1 and 128 comma-separated sizes")
    try:
        return [int(part.strip()) for part in parts]
    except ValueError as exc:
        raise ValueError("Payload sizes must be integers in bytes") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare invented optical/electrical link assumptions offline."
    )
    parser.add_argument(
        "--sizes", default="64,4096,65536,1048576",
        help="Comma-separated payload byte counts (synthetic, no traffic generated)",
    )
    parser.add_argument(
        "--optical-conversion-us", type=float, default=ILLUSTRATIVE_OPTICAL.conversion_latency_us
    )
    parser.add_argument(
        "--optical-idle-w", type=float, default=ILLUSTRATIVE_OPTICAL.idle_power_w
    )
    parser.add_argument(
        "--optical-bandwidth-gbps", type=float, default=ILLUSTRATIVE_OPTICAL.bandwidth_gbps
    )
    args = parser.parse_args(argv)
    try:
        optical = LinkAssumptions(
            label="operator-supplied synthetic optical estimate",
            bandwidth_gbps=args.optical_bandwidth_gbps,
            base_latency_us=ILLUSTRATIVE_OPTICAL.base_latency_us,
            conversion_latency_us=args.optical_conversion_us,
            idle_power_w=args.optical_idle_w,
            dynamic_energy_pj_per_bit=ILLUSTRATIVE_OPTICAL.dynamic_energy_pj_per_bit,
            setup_energy_uj=ILLUSTRATIVE_OPTICAL.setup_energy_uj,
        )
        report = compare_paths(_parse_sizes(args.sizes), optical=optical)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
