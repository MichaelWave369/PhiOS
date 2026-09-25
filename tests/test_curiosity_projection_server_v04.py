from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from phios.curiosity import CuriosityArtifact
from phios.curiosity_projection_server import (
    LOOPBACK_HOST,
    CuriosityProjectionServer,
    build_curiosity_projection,
)
from phios.curiosity_store import (
    CuriosityReturnPointer,
    CuriosityStore,
)


def _seed_store(tmp_path: Path) -> tuple[CuriosityStore, CuriosityArtifact]:
    store = CuriosityStore(tmp_path / "curiosity")
    artifact = CuriosityArtifact.build(
        artifact_kind="symbol",
        title="Nested bubble gear",
        content="A symbolic recursive structure.",
        created_at="2026-09-25T20:00:00+00:00",
        created_by="operator:mikey",
        tags=("bubble", "gear"),
    )
    store.append_artifact(artifact)
    store.append_return_pointer(
        CuriosityReturnPointer.build(
            artifact_sha256=artifact.curiosity_artifact_sha256,
            created_at="2026-09-25T20:10:00+00:00",
            created_by="operator:mikey",
            return_prompt="Return to the rhythm connection.",
        )
    )
    return store, artifact


def test_projection_exposes_canonical_store_without_authority(
    tmp_path: Path,
) -> None:
    store, artifact = _seed_store(tmp_path)

    projection = build_curiosity_projection(store, limit=16)

    assert projection["persistent"] is True
    assert projection["writeAvailable"] is False
    assert projection["writeHoldReason"] == (
        "action_lease_broker_unavailable"
    )
    assert projection["count"] == 1
    assert projection["operationalAuthority"] is False
    assert projection["actionAuthority"] is False
    assert projection["executionAuthority"] is False
    assert projection["effectPerformed"] is False

    artifacts = projection["artifacts"]
    assert isinstance(artifacts, list)
    assert artifacts[0]["curiosity_artifact_sha256"] == (
        artifact.curiosity_artifact_sha256
    )


def test_loopback_server_reads_store_and_holds_browser_writes(
    tmp_path: Path,
) -> None:
    store, artifact = _seed_store(tmp_path)
    server = CuriosityProjectionServer((LOOPBACK_HOST, 0), store)
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()
    port = int(server.server_address[1])

    try:
        connection = http.client.HTTPConnection(
            LOOPBACK_HOST,
            port,
            timeout=2,
        )
        connection.request("GET", "/api/v1/curiosity?limit=16")
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 200
        assert response.getheader("access-control-allow-origin") is None
        assert body["localOnly"] is True
        assert body["readOnly"] is True
        assert body["executionAuthority"] is False
        assert body["projection"]["artifacts"][0][
            "curiosity_artifact_sha256"
        ] == artifact.curiosity_artifact_sha256
        connection.close()

        connection = http.client.HTTPConnection(
            LOOPBACK_HOST,
            port,
            timeout=2,
        )
        connection.request(
            "POST",
            "/api/v1/curiosity/artifacts",
            body=b"{}",
            headers={"content-type": "application/json"},
        )
        response = connection.getresponse()
        held = json.loads(response.read())
        assert response.status == 428
        assert held["error"] == "action_lease_required"
        assert held["writeAvailable"] is False
        assert held["actionAuthority"] is False
        assert held["executionAuthority"] is False
        assert held["effectPerformed"] is False
        assert len(store.artifacts()) == 1
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_projection_limit_is_bounded(tmp_path: Path) -> None:
    store, _artifact = _seed_store(tmp_path)

    try:
        build_curiosity_projection(store, limit=65)
    except ValueError as exc:
        assert "between 1 and 64" in str(exc)
    else:
        raise AssertionError("limit 65 should fail")
