import json
from pathlib import Path

from phios.mandala import MandalaStatus
from phios.reality import (
    LocalHttpObservation,
    LocalHttpObservationError,
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
)
from phios.spine.runtime import PhiOSSpine


class FakeHttpProvider:
    name = "fake-http"

    def __init__(
        self,
        observation: LocalHttpObservation | None = None,
        *,
        error: LocalHttpObservationError | None = None,
    ) -> None:
        self.observation = observation
        self.error = error
        self.calls: list[tuple[str, float, int]] = []

    def observe(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> LocalHttpObservation:
        self.calls.append((url, timeout_seconds, max_body_bytes))
        if self.error is not None:
            raise self.error
        assert self.observation is not None
        return self.observation


def _observation(
    *,
    url: str = "http://127.0.0.1:8000/health",
    status: int = 200,
) -> LocalHttpObservation:
    return LocalHttpObservation(
        url=url,
        method="GET",
        status_code=status,
        reason="OK" if status == 200 else "OTHER",
        headers={
            "content-type": "application/json",
            "content-length": "15",
        },
        body_sha256="a" * 64,
        body_bytes_observed=15,
        body_truncated=False,
        body_digest_scope="full",
        redirect_followed=False,
        timeout_seconds=2.0,
        max_body_bytes=65_536,
        elapsed_ms=4.25,
        provider="fake-http",
        provider_version="1.0",
        captured_at_utc="2026-09-18T17:30:00+00:00",
    )


def _claim(
    *,
    url: str = "http://127.0.0.1:8000/health",
    expected_status: int = 200,
) -> RealityClaim:
    return RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE,
        statement=f"{url} returns HTTP {expected_status}.",
        http_url=url,
        expected_http_status=expected_status,
    )


def test_local_http_still_requires_reality_verify(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.local_http.read"],
        task_id="http-base-denied",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "missing_grant:reality.verify" in result.receipt.limitations


def test_local_http_requires_specific_read_grant(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify"],
        task_id="http-read-denied",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert result.claim_results[0]["verdict"] == RealityVerdict.BLOCKED.value
    assert provider.calls == []
    assert result.claim_results[0]["reason"] == "missing_grant:reality.local_http.read"


def test_exact_http_status_can_support_claim(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation(status=200))
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-supported",
    )

    result = spine.verify_reality(
        claims=(_claim(expected_status=200),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    claim_result = result.claim_results[0]
    assert claim_result["verdict"] == RealityVerdict.SUPPORTED.value
    assert claim_result["observed_http_status"] == 200
    assert claim_result["redirect_followed"] is False

    evidence_ref = claim_result["observation_evidence_ref"]
    assert evidence_ref in result.receipt.evidence_used
    observation = json.loads(spine.soma.evidence.read_bytes(evidence_ref))
    assert observation["status_code"] == 200
    assert observation["body_sha256"] == "a" * 64


def test_http_status_conflict_is_disputed(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation(status=503))
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-conflict",
    )
    claim = _claim(expected_status=200)

    result = spine.verify_reality(
        claims=(claim,),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.DISPUTED
    assert result.claim_results[0]["verdict"] == RealityVerdict.CONTRADICTED.value


def test_unavailable_http_provider_is_unresolved(tmp_path: Path) -> None:
    provider = FakeHttpProvider(
        error=LocalHttpObservationError(
            "local_http_provider_unavailable",
            "no adapter",
        )
    )
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-unresolved",
    )

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["verdict"] == RealityVerdict.UNRESOLVED.value
    assert result.claim_results[0]["reason"] == "local_http_provider_unavailable"


def test_remote_http_url_is_blocked_before_provider(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-remote-blocked",
    )
    claim = _claim(url="http://192.168.1.1/health")

    result = spine.verify_reality(
        claims=(claim,),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "local_http_claim_requires_loopback_host" in result.receipt.limitations


def test_https_is_blocked_in_v013(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-https-blocked",
    )
    claim = _claim(url="https://127.0.0.1:8443/health")

    result = spine.verify_reality(
        claims=(claim,),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "local_http_claim_requires_http_scheme" in result.receipt.limitations


def test_invalid_http_budget_is_blocked_before_provider(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-budget",
    )
    claim = RealityClaim.create(
        kind=RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE,
        statement="Local health endpoint returns 200.",
        http_url="http://localhost:8000/health",
        expected_http_status=200,
        http_max_body_bytes=0,
    )

    result = spine.verify_reality(
        claims=(claim,),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == []
    assert "local_http_claim_invalid_body_budget" in result.receipt.limitations


def test_default_http_transport_fails_closed(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-default-unavailable",
    )

    result = spine.verify_reality(claims=(_claim(),))

    assert result.receipt.status is MandalaStatus.UNKNOWN
    assert result.claim_results[0]["reason"] == "local_http_provider_unavailable"


def test_http_verifier_does_not_expand_authority(tmp_path: Path) -> None:
    provider = FakeHttpProvider(_observation())
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["reality.verify", "reality.local_http.read"],
        task_id="http-authority",
    )
    before = spine.core.authority

    result = spine.verify_reality(
        claims=(_claim(),),
        local_http_provider=provider,
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
