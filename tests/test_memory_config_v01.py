import json
from pathlib import Path

import pytest

from phios.memory.config import MemoryRuntimeConfig, write_disabled_template


def test_disabled_default_is_fail_closed() -> None:
    config = MemoryRuntimeConfig.disabled_default()
    assert config.enabled is False
    assert config.semantic_enabled is False
    assert config.principal_id == "operator"


def test_unknown_config_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown memory config fields"):
        MemoryRuntimeConfig.from_mapping({"enabled": False, "surprise": True})


def test_semantic_config_requires_model_and_dimensions() -> None:
    with pytest.raises(ValueError, match="embedding_model"):
        MemoryRuntimeConfig.from_mapping({"semantic_enabled": True})
    with pytest.raises(ValueError, match="embedding_dimensions"):
        MemoryRuntimeConfig.from_mapping(
            {"semantic_enabled": True, "embedding_model": "embeddinggemma"}
        )


def test_disabled_template_is_written_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    write_disabled_template(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["enabled"] is False
    assert payload["semantic_enabled"] is False
    with pytest.raises(FileExistsError):
        write_disabled_template(path)
