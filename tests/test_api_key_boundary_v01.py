import json
from pathlib import Path

import pytest

from phios.spine import (
    ApiKeyBoundary,
    ApiKeyContractError,
    InboundApiKeySpec,
    OutboundApiKeySpec,
    PhiOSSpine,
)


def test_inbound_api_key_authenticates_without_receipting_secret() -> None:
    secret = "phios-test-inbound-secret-123"
    boundary = ApiKeyBoundary()
    boundary.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id="operator-input",
            audience="phios.operator",
            secret=secret,
            scopes=("memory.read", "reality.verify"),
        )
    )

    receipt = boundary.authenticate_inbound(
        key_id="operator-input",
        presented_key=secret,
        audience="phios.operator",
    )

    assert receipt.authenticated is True
    assert receipt.scopes == ("memory.read", "reality.verify")
    assert receipt.credential_exposed is False
    assert receipt.operational_authority is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    serialized = json.dumps(receipt.to_dict(), sort_keys=True)
    assert secret not in serialized


def test_wrong_inbound_api_key_fails_closed_without_scope_leak() -> None:
    boundary = ApiKeyBoundary()
    boundary.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id="operator-input",
            audience="phios.operator",
            secret="correct-secret",
            scopes=("artifact.write",),
        )
    )

    receipt = boundary.authenticate_inbound(
        key_id="operator-input",
        presented_key="wrong-secret",
        audience="phios.operator",
    )

    assert receipt.authenticated is False
    assert receipt.status == "DENIED"
    assert receipt.reason == "inbound_key_mismatch"
    assert receipt.scopes == ()
    serialized = json.dumps(receipt.to_dict(), sort_keys=True)
    assert "correct-secret" not in serialized
    assert "wrong-secret" not in serialized


def test_inbound_audience_mismatch_fails_closed() -> None:
    boundary = ApiKeyBoundary()
    boundary.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id="bridge-input",
            audience="xi.bridge",
            secret="bridge-secret",
            scopes=("bridge.read",),
        )
    )

    receipt = boundary.authenticate_inbound(
        key_id="bridge-input",
        presented_key="bridge-secret",
        audience="other.service",
    )

    assert receipt.authenticated is False
    assert receipt.reason == "inbound_key_audience_mismatch"
    assert receipt.scopes == ()


def test_outbound_api_key_is_resolved_ephemerally_from_environment() -> None:
    secret = "provider-secret-never-receipted"

    def env(name: str) -> str | None:
        return secret if name == "EXAMPLE_PROVIDER_API_KEY" else None

    boundary = ApiKeyBoundary(environment_getter=env)
    boundary.register_outbound(
        OutboundApiKeySpec(
            key_id="example-output",
            provider="example-provider",
            environment_variable="EXAMPLE_PROVIDER_API_KEY",
            scopes=("api.read",),
        )
    )

    lease = boundary.lease_outbound(
        key_id="example-output",
        provider="example-provider",
    )

    headers = lease.authorization_headers({"Accept": "application/json"})
    assert headers["Authorization"] == f"Bearer {secret}"
    assert headers["Accept"] == "application/json"
    assert secret not in repr(lease)
    assert secret not in json.dumps(lease.metadata(), sort_keys=True)
    assert secret not in json.dumps(lease.receipt.to_dict(), sort_keys=True)
    assert "EXAMPLE_PROVIDER_API_KEY" not in json.dumps(
        lease.receipt.to_dict(),
        sort_keys=True,
    )
    assert lease.receipt.credential_exposed is False
    assert lease.receipt.action_authority is False
    assert lease.receipt.execution_authority is False


def test_outbound_api_key_supports_x_api_key_style_header() -> None:
    boundary = ApiKeyBoundary(
        environment_getter=lambda name: "x-secret" if name == "X_API_KEY" else None
    )
    boundary.register_outbound(
        OutboundApiKeySpec(
            key_id="vendor-output",
            provider="vendor",
            environment_variable="X_API_KEY",
            header_name="X-API-Key",
            header_prefix="",
        )
    )

    lease = boundary.lease_outbound(
        key_id="vendor-output",
        provider="vendor",
    )

    assert lease.authorization_headers() == {"X-API-Key": "x-secret"}


def test_outbound_provider_mismatch_and_missing_secret_fail_without_leak() -> None:
    boundary = ApiKeyBoundary(environment_getter=lambda _name: None)
    boundary.register_outbound(
        OutboundApiKeySpec(
            key_id="example-output",
            provider="example-provider",
            environment_variable="EXAMPLE_PROVIDER_API_KEY",
        )
    )

    with pytest.raises(ApiKeyContractError, match="provider mismatch"):
        boundary.lease_outbound(
            key_id="example-output",
            provider="different-provider",
        )
    with pytest.raises(ApiKeyContractError, match="unavailable"):
        boundary.lease_outbound(
            key_id="example-output",
            provider="example-provider",
        )


def test_outbound_lease_refuses_credential_header_overwrite() -> None:
    boundary = ApiKeyBoundary(
        environment_getter=lambda name: "secret" if name == "SERVICE_KEY" else None
    )
    boundary.register_outbound(
        OutboundApiKeySpec(
            key_id="service-output",
            provider="service",
            environment_variable="SERVICE_KEY",
        )
    )
    lease = boundary.lease_outbound(
        key_id="service-output",
        provider="service",
    )

    with pytest.raises(ApiKeyContractError, match="ambiguous overwrite"):
        lease.authorization_headers({"authorization": "already-present"})


def test_key_ids_are_unique_across_input_and_output_directions() -> None:
    boundary = ApiKeyBoundary()
    boundary.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id="shared-slot",
            audience="phios",
            secret="input-secret",
        )
    )

    with pytest.raises(ApiKeyContractError, match="unique across directions"):
        boundary.register_outbound(
            OutboundApiKeySpec(
                key_id="shared-slot",
                provider="provider",
                environment_variable="PROVIDER_API_KEY",
            )
        )


def test_spine_exposes_input_and_output_key_boundary(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=(),
        task_id="api-key-boundary",
    )
    spine.api_keys.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id="input",
            audience="phios",
            secret="inbound-secret",
        )
    )

    receipt = spine.api_keys.authenticate_inbound(
        key_id="input",
        presented_key="inbound-secret",
        audience="phios",
    )

    assert receipt.authenticated is True
    assert spine.core.authority.grants == ()
    assert receipt.action_authority is False


def test_inbound_header_helper_supports_api_gateway_style_input() -> None:
    boundary = ApiKeyBoundary()
    boundary.register_inbound(
        InboundApiKeySpec.from_secret(
            key_id="gateway-input",
            audience="phios.http",
            secret="gateway-secret",
            scopes=("request.submit",),
        )
    )

    accepted = boundary.authenticate_inbound_headers(
        key_id="gateway-input",
        headers={"X-API-Key": "gateway-secret"},
        audience="phios.http",
    )
    missing = boundary.authenticate_inbound_headers(
        key_id="gateway-input",
        headers={},
        audience="phios.http",
    )

    assert accepted.authenticated is True
    assert accepted.scopes == ("request.submit",)
    assert missing.authenticated is False
    assert missing.reason == "inbound_key_header_missing"
