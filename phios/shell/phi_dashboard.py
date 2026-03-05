"""ANSI living dashboard for PhiOS."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from phios.core.brainc_client import ollama_available
from phios.core.lt_engine import compute_lt
from phios.core.sovereignty import SovereignSnapshot
from phios.core.tbrc_bridge import TBRCBridge
from phios.network.discovery import PhiNodeAnnouncer, PhiNodeDiscovery, PhiPeerDict


class PhiDashboard:
    def __init__(self, announcer: PhiNodeAnnouncer | None = None, discovery: PhiNodeDiscovery | None = None) -> None:
        self.bridge = TBRCBridge()
        self.snapshotter = SovereignSnapshot()
        self.session_start = time.monotonic()
        self.announcer = announcer if announcer is not None else PhiNodeAnnouncer()
        self.discovery = discovery if discovery is not None else PhiNodeDiscovery()

    def _rhythm_line(self, elapsed: int) -> str:
        marker = "●" if elapsed > 0 and elapsed % 369 == 0 else "○"
        next_nine = 9 - (elapsed % 9)
        if next_nine == 9:
            next_nine = 0
        return f"Rhythm 3-6-9 {marker} | next-9:{next_nine:02d}s | t={elapsed}s"

    def render_network_panel(self, peers: list[PhiPeerDict]) -> list[str]:
        if not peers:
            return ["NETWORK · offline", "(phi network announce to join)"]
        lines = [f"NETWORK · {len(peers)} peers"]
        for peer in peers[:5]:
            lines.append(
                f"● {peer['node_name'][:12]:12} lt {peer['lt_score']:.2f} {'✓' if peer['tbrc'] else '✗'} TBRC {'✓' if peer['phb'] else '✗'} PHB"
            )
        return lines

    def render_network_lt_blend(self, local_lt: float, peers: list[PhiPeerDict]) -> str:
        if not peers:
            return f"Network L(t): {local_lt:.3f} (local: {local_lt:.3f} · 0 peers · avg)"
        avg = (local_lt + sum(float(peer.get("lt_score", 0.0)) for peer in peers)) / (len(peers) + 1)
        return f"Network L(t): {avg:.3f} (local: {local_lt:.3f} · {len(peers)} peers · avg)"

    def render(self, now_s: int | None = None) -> str:
        elapsed = now_s if now_s is not None else int(time.monotonic() - self.session_start)
        lt = compute_lt()
        tbrc = self.bridge.full_status()
        archive = self.bridge.get_archive_timeline(limit=3)

        active = tbrc.get("active_session") if isinstance(tbrc, dict) else None
        phb = self.bridge.get_phb_status()
        kg = self.bridge.get_kg_summary()

        lines = [
            "=" * 80,
            "PhiOS Living Dashboard",
            "=" * 80,
            f"Coherence | L(t): {float(lt.get('lt', 0.0)):.3f} | psi_b: {float(lt.get('components', {}).get('A_stability', 0.0)):.3f} | G: {float(lt.get('components', {}).get('G_load', 0.0)):.3f} | C: {float(lt.get('components', {}).get('C_variance', 0.0)):.3f} | trajectory: stable",
            (
                "Research  | session: none"
                if not active
                else f"Research  | session: active | preset:{active.get('preset', 'unknown')} | engine:{active.get('engine', 'unknown')} | duration:{active.get('duration_s', 0)}s | session L(t):{float(active.get('lt', 0.0)):.3f}"
            ),
            f"Hardware  | PHB connected:{bool(phb.get('connected', False)) if isinstance(phb, dict) else False} | sensors:{int(phb.get('sensor_count', 0)) if isinstance(phb, dict) else 0} | calibration age:{phb.get('calibration_age_s', 'n/a') if isinstance(phb, dict) else 'n/a'} | signal:[####-----]",
            f"Intel     | BrainC:{'yes' if ollama_available() else 'no'} | KG nodes:{int(kg.get('nodes', 0)) if isinstance(kg, dict) else 0} | Memory entries:{int(tbrc.get('memory_entries', 0)) if isinstance(tbrc, dict) else 0}",
            "Archive   | " + (" | ".join(item.get("title", "untitled") for item in archive[:3]) if archive else "no milestones"),
        ]

        if self.announcer.active and self.discovery.active:
            peers = self.discovery.get_peers()
            lines.extend(self.render_network_panel(peers))
            lines.append(self.render_network_lt_blend(float(lt.get("lt", 0.0)), peers))

        lines.extend([
            self._rhythm_line(elapsed),
            "Keys: [q] quit [r] refresh [s] snapshot [a] archive add [n] network [?] help",
        ])
        return "\n".join(lines)

    def handle_snapshot(self) -> dict[str, object]:
        lt = compute_lt()
        session_data = {"history": [], "duration_s": int(time.monotonic() - self.session_start), "commands_run": 0, "resonance_moments_hit": 0, "trajectory": "stable"}
        snap = self.snapshotter.capture(lt, session_data)
        out = Path(f"phi_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        out.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        if self.bridge.is_available():
            self.bridge.memorize_phi_snapshot(dict(snap))
        return {"snapshot": str(out)}

    def handle_archive_add(self, title: str, narrative: str, significance: str, confirmed: bool) -> dict[str, object]:
        if not confirmed:
            return {"added": False, "reason": "operator confirmation required"}
        return self.bridge.add_archive_milestone(title, narrative, significance, operator_confirmed=True)

    def run(self) -> None:
        try:
            while True:
                print("\x1b[2J\x1b[H" + self.render(), flush=True)
                if self.announcer.active:
                    self.announcer.update_lt(float(compute_lt().get("lt", 0.0)))
                time.sleep(3)
        except KeyboardInterrupt:
            return
