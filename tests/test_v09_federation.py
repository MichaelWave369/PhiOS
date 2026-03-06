from __future__ import annotations

import json
import socket

from phios.network.discovery import PhiNodeAnnouncer, PhiNodeDiscovery, PhiPeerDict
from phios.network.exchange import ExchangeLog, PhiExchangeClient, PhiExchangeServer
from phios.shell.phi_commands import cmd_exchange, cmd_network
from phios.shell.phi_dashboard import PhiDashboard


def test_announcer_requires_operator_confirmed() -> None:
    announcer = PhiNodeAnnouncer()
    assert announcer.announce("node", operator_confirmed=False) is False


def test_announcer_degrades_without_zeroconf() -> None:
    announcer = PhiNodeAnnouncer()
    assert announcer.announce("node", operator_confirmed=True) is False


def test_discovery_returns_typed_peer_list() -> None:
    discovery = PhiNodeDiscovery()
    discovery.active = True
    peer: PhiPeerDict = {
        "node_name": "node",
        "address": "127.0.0.1",
        "port": 36900,
        "phios_version": "0.9.0",
        "lt_score": 0.7,
        "tbrc": False,
        "phb": False,
        "last_seen": "2024-01-01T00:00:00+00:00",
        "reachable": False,
    }
    discovery.inject_peer_for_tests(peer)
    peers = discovery.get_peers()
    assert isinstance(peers, list)
    assert isinstance(peers[0], dict)


def test_peer_dict_schema_correct() -> None:
    keys = PhiPeerDict.__annotations__.keys()
    expected = {"node_name", "address", "port", "phios_version", "lt_score", "tbrc", "phb", "last_seen", "reachable"}
    assert set(keys) == expected


def test_announced_fields_no_sensitive_data() -> None:
    payload = PhiNodeAnnouncer().preview_payload("")
    assert set(payload.keys()) == {"node_name", "phios_version", "lt_score", "tbrc", "phb"}
    assert "/" not in payload["node_name"]


def test_discovery_off_by_default() -> None:
    assert PhiNodeDiscovery().active is False


def test_ping_peer_never_raises(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(socket, "create_connection", _boom)
    assert PhiNodeDiscovery().ping_peer("127.0.0.1") is False


def test_peers_list_empty_when_none_found() -> None:
    discovery = PhiNodeDiscovery()
    discovery.active = True
    assert discovery.get_peers() == []


def test_exchange_propose_requires_confirmed(tmp_path) -> None:
    snap = tmp_path / "s.json"
    snap.write_text("{}", encoding="utf-8")
    out = PhiExchangeClient(server=PhiExchangeServer()).propose_exchange("127.0.0.1", str(snap), operator_confirmed=False)
    assert out["status"] == "refused"


def test_exchange_accept_requires_confirmed() -> None:
    out = PhiExchangeServer().accept_proposal("id", operator_confirmed=False)
    assert out["accepted"] is False


def test_exchange_verifies_hash_on_receipt() -> None:
    server = PhiExchangeServer()
    payload = "{}"
    import hashlib

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    server.submit_proposal({"proposal_id": "abc", "from_node": "n", "snapshot_hash": digest, "payload": payload})
    out = server.accept_proposal("abc", operator_confirmed=True)
    assert out["verified"] is True


def test_exchange_logs_sent_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    server = PhiExchangeServer()
    client = PhiExchangeClient(server=server)
    snap = tmp_path / "s.json"
    snap.write_text("{}", encoding="utf-8")
    proposal = client.propose_exchange("127.0.0.1", str(snap), operator_confirmed=True)
    server.accept_proposal(proposal["proposal_id"], operator_confirmed=True)
    out = client.send_snapshot("127.0.0.1", str(snap), proposal["proposal_id"])
    assert out["status"] == "sent"
    assert client.log.get_history(limit=1)[0]["direction"] == "sent"


def test_exchange_logs_received_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    server = PhiExchangeServer()
    payload = "{}"
    import hashlib

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    server.submit_proposal({"proposal_id": "abc", "from_node": "n", "snapshot_hash": digest, "payload": payload})
    server.accept_proposal("abc", operator_confirmed=True)
    assert server.log.get_history(limit=1)[0]["direction"] == "received"


def test_exchange_reject_transfers_no_data() -> None:
    server = PhiExchangeServer()
    server.submit_proposal({"proposal_id": "abc", "from_node": "n", "snapshot_hash": "x", "payload": None})
    server.reject_proposal("abc")
    assert server.get_pending_proposals() == []


def test_exchange_history_max_9(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    log = ExchangeLog()
    for i in range(12):
        log.log_sent(f"n{i}", str(i))
    assert len(log.get_history(limit=9)) == 9


def test_exchange_server_degrades_on_port_conflict(monkeypatch) -> None:
    class FakeSock:
        def setsockopt(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            raise OSError("in use")

        def listen(self, n):
            return None

        def close(self):
            return None

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: FakeSock())
    server = PhiExchangeServer()
    server.start()
    assert server.running is False


def test_dashboard_network_panel_renders() -> None:
    dashboard = PhiDashboard()
    lines = dashboard.render_network_panel([
        {
            "node_name": "n1",
            "address": "127.0.0.1",
            "port": 36900,
            "phios_version": "0.9.0",
            "lt_score": 0.8,
            "tbrc": True,
            "phb": False,
            "last_seen": "x",
            "reachable": True,
        }
    ])
    assert lines[0].startswith("NETWORK")


def test_dashboard_network_panel_offline_message() -> None:
    lines = PhiDashboard().render_network_panel([])
    assert "offline" in lines[0]


def test_dashboard_network_lt_blend_correct() -> None:
    dashboard = PhiDashboard()
    peers = [
        {"node_name": "a", "address": "1", "port": 36900, "phios_version": "0.9.0", "lt_score": 0.6, "tbrc": False, "phb": False, "last_seen": "x", "reachable": True},
        {"node_name": "b", "address": "2", "port": 36900, "phios_version": "0.9.0", "lt_score": 0.9, "tbrc": False, "phb": False, "last_seen": "x", "reachable": True},
    ]
    line = dashboard.render_network_lt_blend(0.9, peers)
    assert "0.800" in line


def test_dashboard_network_panel_max_peers_shown() -> None:
    dashboard = PhiDashboard()
    peers = [{"node_name": f"n{i}", "address": str(i), "port": 36900, "phios_version": "0.9.0", "lt_score": 0.1, "tbrc": False, "phb": False, "last_seen": "x", "reachable": True} for i in range(9)]
    lines = dashboard.render_network_panel(peers)
    assert len(lines) == 6


def test_dashboard_renders_without_network() -> None:
    text = PhiDashboard().render(now_s=1)
    assert "NETWORK" not in text


def test_phi_network_status_schema() -> None:
    data = json.loads(cmd_network(["status"]))
    assert {"discovery_active", "announcer_active", "peer_count", "announced", "exchange", "network_mode"}.issubset(data.keys())


def test_phi_network_announce_requires_confirm() -> None:
    out = cmd_network(["announce"])
    assert "Confirmation required" in out


def test_phi_network_peers_returns_list() -> None:
    out = cmd_network(["peers"])
    assert "NETWORK" in out


def test_phi_exchange_pending_returns_list() -> None:
    out = cmd_exchange(["pending"])
    data = json.loads(out)
    assert isinstance(data, list)


def test_phi_exchange_history_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PHIOS_CONFIG_HOME", str(tmp_path))
    log = ExchangeLog()
    log.log_sent("node", "abc")
    out = json.loads(cmd_exchange(["history"]))
    assert isinstance(out, list)
