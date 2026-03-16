from __future__ import annotations

import json

from phios.shell.phi_router import route_command


def test_shell_memory_topic_and_coherence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHIOS_MCP_CAPABILITIES", "agent_memory_write")

    payload = '[{"figure":"Architect","claim":"scope first","stance":"pro"}]'
    out_store, code_store = route_command(
        [
            "memory",
            "store",
            "alpha",
            "--positions",
            payload,
            "--outcome",
            "consensus",
            "--winner",
            "Architect",
            "--trace",
            "0.2,0.4,0.6",
            "--tags",
            "x,y",
            "--yes",
        ]
    )
    assert code_store == 0
    stored = json.loads(out_store)
    assert stored["ok"] is True

    out_topic, code_topic = route_command(["memory", "topic", "alpha"])
    assert code_topic == 0
    topic = json.loads(out_topic)
    assert topic["found"] is True

    out_coh, code_coh = route_command(["memory", "coherence", "alpha"])
    assert code_coh == 0
    coh = json.loads(out_coh)
    assert coh["count"] == 1
