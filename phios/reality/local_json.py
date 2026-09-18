from __future__ import annotations

import json
from typing import Any

JSON_TYPE_NAMES = frozenset(
    {
        "object",
        "array",
        "string",
        "number",
        "integer",
        "boolean",
        "null",
    }
)


def json_pointer_error(pointer: str | None) -> str | None:
    if pointer is None:
        return "local_http_json_claim_requires_pointer"
    if len(pointer) > 512:
        return "local_http_json_claim_pointer_too_long"
    if pointer == "":
        return None
    if not pointer.startswith("/"):
        return "local_http_json_claim_invalid_pointer"

    tokens = pointer.split("/")[1:]
    if len(tokens) > 32:
        return "local_http_json_claim_pointer_too_deep"

    for token in tokens:
        index = 0
        while index < len(token):
            if token[index] != "~":
                index += 1
                continue
            if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
                return "local_http_json_claim_invalid_pointer_escape"
            index += 2
    return None


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document

    current = document
    for encoded_token in pointer.split("/")[1:]:
        token = _decode_pointer_token(encoded_token)
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
            continue

        if isinstance(current, list):
            if token == "0":
                index = 0
            elif token.isdigit() and not token.startswith("0"):
                index = int(token)
            else:
                return False, None
            if not 0 <= index < len(current):
                return False, None
            current = current[index]
            continue

        return False, None

    return True, current


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError("value is not representable as a JSON type")


def json_type_matches(value: Any, expected_type: str) -> bool:
    actual = json_type_name(value)
    if expected_type == "number":
        return actual in {"integer", "number"}
    return actual == expected_type


def strict_json_loads(data: bytes) -> Any:
    text = data.decode("utf-8")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(text, parse_constant=reject_constant)
