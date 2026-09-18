from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
    if isinstance(value, (float, Decimal)):
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

    return json.loads(
        text,
        parse_constant=reject_constant,
        parse_float=Decimal,
    )


JSON_STRUCTURAL_PREDICATES = frozenset(
    {
        "string_non_empty",
        "array_length_eq",
        "array_length_gte",
        "array_length_lte",
        "object_key_count_eq",
        "object_key_count_gte",
        "object_key_count_lte",
    }
)

_JSON_PREDICATE_EXPECTED_TYPES = {
    "string_non_empty": "string",
    "array_length_eq": "array",
    "array_length_gte": "array",
    "array_length_lte": "array",
    "object_key_count_eq": "object",
    "object_key_count_gte": "object",
    "object_key_count_lte": "object",
}


def json_structural_predicate_error(
    predicate: str | None,
    bound: int | None,
) -> str | None:
    if predicate is None:
        return "local_http_json_predicate_requires_kind"
    if predicate not in JSON_STRUCTURAL_PREDICATES:
        return "local_http_json_predicate_invalid_kind"

    if predicate == "string_non_empty":
        if bound is not None:
            return "local_http_json_predicate_disallows_bound"
        return None

    if bound is None:
        return "local_http_json_predicate_requires_bound"
    if (
        isinstance(bound, bool)
        or not isinstance(bound, int)
        or not 0 <= bound <= 1_000_000
    ):
        return "local_http_json_predicate_invalid_bound"
    return None


def json_structural_predicate_expected_type(predicate: str) -> str:
    return _JSON_PREDICATE_EXPECTED_TYPES[predicate]


def evaluate_json_structural_predicate(
    value: Any,
    *,
    predicate: str,
    bound: int | None,
) -> dict[str, Any]:
    expected_type = json_structural_predicate_expected_type(predicate)
    observed_type = json_type_name(value)
    result: dict[str, Any] = {
        "predicate": predicate,
        "expected_json_type": expected_type,
        "observed_json_type": observed_type,
        "type_matches": observed_type == expected_type,
        "bound": bound,
        "measurement_name": None,
        "measurement": None,
        "predicate_matches": False,
    }
    if observed_type != expected_type:
        return result

    if predicate == "string_non_empty":
        assert isinstance(value, str)
        result["measurement_name"] = "is_non_empty"
        result["measurement"] = bool(value)
        result["predicate_matches"] = bool(value)
        return result

    assert bound is not None
    if predicate.startswith("array_length_"):
        assert isinstance(value, list)
        measurement = len(value)
        result["measurement_name"] = "array_length"
    else:
        assert isinstance(value, dict)
        measurement = len(value)
        result["measurement_name"] = "object_key_count"

    result["measurement"] = measurement
    if predicate.endswith("_eq"):
        result["predicate_matches"] = measurement == bound
    elif predicate.endswith("_gte"):
        result["predicate_matches"] = measurement >= bound
    else:
        result["predicate_matches"] = measurement <= bound
    return result


JSON_SCALAR_PREDICATES = frozenset(
    {
        "boolean_is_true",
        "boolean_is_false",
        "integer_eq",
        "integer_gte",
        "integer_lte",
        "number_eq",
        "number_gte",
        "number_lte",
    }
)

_JSON_SCALAR_PREDICATE_EXPECTED_TYPES = {
    "boolean_is_true": "boolean",
    "boolean_is_false": "boolean",
    "integer_eq": "integer",
    "integer_gte": "integer",
    "integer_lte": "integer",
    "number_eq": "number",
    "number_gte": "number",
    "number_lte": "number",
}


def _decimal_operand(operand: str) -> Decimal:
    if not operand or len(operand) > 64:
        raise ValueError("invalid scalar operand")
    try:
        value = Decimal(operand)
    except InvalidOperation as exc:
        raise ValueError("invalid scalar operand") from exc
    if not value.is_finite():
        raise ValueError("invalid scalar operand")
    return value


def json_scalar_predicate_error(
    predicate: str | None,
    operand: str | None,
) -> str | None:
    if predicate is None:
        return "local_http_json_scalar_predicate_requires_kind"
    if predicate not in JSON_SCALAR_PREDICATES:
        return "local_http_json_scalar_predicate_invalid_kind"

    if predicate.startswith("boolean_"):
        if operand is not None:
            return "local_http_json_scalar_predicate_disallows_operand"
        return None

    if operand is None:
        return "local_http_json_scalar_predicate_requires_operand"
    try:
        numeric = _decimal_operand(operand)
    except ValueError:
        return "local_http_json_scalar_predicate_invalid_operand"

    if predicate.startswith("integer_") and numeric != numeric.to_integral_value():
        return "local_http_json_scalar_predicate_requires_integer_operand"
    return None


def json_scalar_predicate_expected_type(predicate: str) -> str:
    return _JSON_SCALAR_PREDICATE_EXPECTED_TYPES[predicate]


def evaluate_json_scalar_predicate(
    value: Any,
    *,
    predicate: str,
    operand: str | None,
) -> dict[str, Any]:
    expected_type = json_scalar_predicate_expected_type(predicate)
    observed_type = json_type_name(value)
    type_matches = json_type_matches(value, expected_type)
    result: dict[str, Any] = {
        "predicate": predicate,
        "expected_json_type": expected_type,
        "observed_json_type": observed_type,
        "type_matches": type_matches,
        "predicate_matches": False,
    }
    if not type_matches:
        return result

    if predicate == "boolean_is_true":
        assert isinstance(value, bool)
        result["predicate_matches"] = value is True
        return result
    if predicate == "boolean_is_false":
        assert isinstance(value, bool)
        result["predicate_matches"] = value is False
        return result

    assert operand is not None
    expected = _decimal_operand(operand)
    if isinstance(value, int):
        observed = Decimal(value)
    else:
        assert isinstance(value, Decimal)
        observed = value

    if predicate.endswith("_eq"):
        result["predicate_matches"] = observed == expected
    elif predicate.endswith("_gte"):
        result["predicate_matches"] = observed >= expected
    else:
        result["predicate_matches"] = observed <= expected
    return result


@dataclass(frozen=True, kw_only=True)
class JsonMixedContractClause:
    pointer: str
    expected_json_type: str | None = None
    structural_predicate: str | None = None
    structural_bound: int | None = None
    scalar_predicate: str | None = None
    scalar_operand: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "JsonMixedContractClause":
        allowed_keys = {
            "pointer",
            "type",
            "predicate",
            "bound",
            "scalar_predicate",
            "operand",
        }
        unknown_keys = sorted(set(value) - allowed_keys)
        if unknown_keys:
            joined = ",".join(unknown_keys)
            raise ValueError(f"unsupported mixed JSON clause keys: {joined}")
        return cls(
            pointer=str(value.get("pointer", "")),
            expected_json_type=(
                str(value["type"])
                if value.get("type") is not None
                else None
            ),
            structural_predicate=(
                str(value["predicate"])
                if value.get("predicate") is not None
                else None
            ),
            structural_bound=value.get("bound"),
            scalar_predicate=(
                str(value["scalar_predicate"])
                if value.get("scalar_predicate") is not None
                else None
            ),
            scalar_operand=(
                str(value["operand"])
                if value.get("operand") is not None
                else None
            ),
        )

    @property
    def requires_value_read(self) -> bool:
        return self.scalar_predicate is not None

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        pointer_error = json_pointer_error(self.pointer)
        if pointer_error is not None:
            errors.append(pointer_error)

        modes = (
            self.expected_json_type is not None,
            self.structural_predicate is not None,
            self.scalar_predicate is not None,
        )
        if sum(modes) != 1:
            errors.append("local_http_json_mixed_clause_requires_exactly_one_mode")
            return tuple(errors)

        if self.expected_json_type is not None:
            if self.expected_json_type not in JSON_TYPE_NAMES:
                errors.append("local_http_json_mixed_clause_invalid_expected_type")
            if self.structural_bound is not None:
                errors.append("local_http_json_mixed_clause_type_disallows_bound")
            if self.scalar_operand is not None:
                errors.append("local_http_json_mixed_clause_type_disallows_operand")
            return tuple(errors)

        if self.structural_predicate is not None:
            if self.scalar_operand is not None:
                errors.append("local_http_json_mixed_clause_structural_disallows_operand")
            predicate_error = json_structural_predicate_error(
                self.structural_predicate,
                self.structural_bound,
            )
            if predicate_error is not None:
                errors.append(predicate_error)
            return tuple(errors)

        if self.structural_bound is not None:
            errors.append("local_http_json_mixed_clause_scalar_disallows_bound")
        scalar_error = json_scalar_predicate_error(
            self.scalar_predicate,
            self.scalar_operand,
        )
        if scalar_error is not None:
            errors.append(scalar_error)
        return tuple(errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pointer": self.pointer,
            "expected_json_type": self.expected_json_type,
            "structural_predicate": self.structural_predicate,
            "structural_bound": self.structural_bound,
            "scalar_predicate": self.scalar_predicate,
            "scalar_operand": self.scalar_operand,
        }


def evaluate_json_mixed_contract_clause(
    document: Any,
    clause: JsonMixedContractClause,
) -> dict[str, Any]:
    pointer_exists, value = resolve_json_pointer(document, clause.pointer)
    if clause.expected_json_type is not None:
        mode = "type"
    elif clause.structural_predicate is not None:
        mode = "structural"
    else:
        mode = "scalar"

    result: dict[str, Any] = {
        "pointer": clause.pointer,
        "pointer_exists": pointer_exists,
        "mode": mode,
        "expected_json_type": clause.expected_json_type,
        "structural_predicate": clause.structural_predicate,
        "structural_bound": clause.structural_bound,
        "scalar_predicate": clause.scalar_predicate,
        "scalar_operand": clause.scalar_operand,
        "observed_json_type": None,
        "type_matches": None,
        "measurement_name": None,
        "measurement": None,
        "predicate_matches": None,
        "clause_matches": False,
    }
    if not pointer_exists:
        return result

    if mode == "type":
        assert clause.expected_json_type is not None
        observed_type = json_type_name(value)
        matched = json_type_matches(value, clause.expected_json_type)
        result["observed_json_type"] = observed_type
        result["type_matches"] = matched
        result["clause_matches"] = matched
        return result

    if mode == "structural":
        assert clause.structural_predicate is not None
        evaluation = evaluate_json_structural_predicate(
            value,
            predicate=clause.structural_predicate,
            bound=clause.structural_bound,
        )
        for key in (
            "expected_json_type",
            "observed_json_type",
            "type_matches",
            "measurement_name",
            "measurement",
            "predicate_matches",
        ):
            result[key] = evaluation[key]
        result["clause_matches"] = bool(
            evaluation["type_matches"] and evaluation["predicate_matches"]
        )
        return result

    assert clause.scalar_predicate is not None
    evaluation = evaluate_json_scalar_predicate(
        value,
        predicate=clause.scalar_predicate,
        operand=clause.scalar_operand,
    )
    for key in (
        "expected_json_type",
        "observed_json_type",
        "type_matches",
        "predicate_matches",
    ):
        result[key] = evaluation[key]
    result["clause_matches"] = bool(
        evaluation["type_matches"] and evaluation["predicate_matches"]
    )
    return result


@dataclass(frozen=True, kw_only=True)
class JsonContractClause:
    pointer: str
    expected_json_type: str | None = None
    predicate: str | None = None
    bound: int | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "JsonContractClause":
        allowed_keys = {"pointer", "type", "predicate", "bound"}
        unknown_keys = sorted(set(value) - allowed_keys)
        if unknown_keys:
            joined = ",".join(unknown_keys)
            raise ValueError(f"unsupported JSON clause keys: {joined}")
        return cls(
            pointer=str(value.get("pointer", "")),
            expected_json_type=(
                str(value["type"])
                if value.get("type") is not None
                else None
            ),
            predicate=(
                str(value["predicate"])
                if value.get("predicate") is not None
                else None
            ),
            bound=value.get("bound"),
        )

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        pointer_error = json_pointer_error(self.pointer)
        if pointer_error is not None:
            errors.append(pointer_error)

        has_type = self.expected_json_type is not None
        has_predicate = self.predicate is not None
        if has_type == has_predicate:
            errors.append("local_http_json_multi_clause_requires_exactly_one_mode")
            return tuple(errors)

        if has_type:
            if self.expected_json_type not in JSON_TYPE_NAMES:
                errors.append("local_http_json_multi_clause_invalid_expected_type")
            if self.bound is not None:
                errors.append("local_http_json_multi_clause_type_disallows_bound")
            return tuple(errors)

        predicate_error = json_structural_predicate_error(
            self.predicate,
            self.bound,
        )
        if predicate_error is not None:
            errors.append(predicate_error)
        return tuple(errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pointer": self.pointer,
            "expected_json_type": self.expected_json_type,
            "predicate": self.predicate,
            "bound": self.bound,
        }


def evaluate_json_contract_clause(
    document: Any,
    clause: JsonContractClause,
) -> dict[str, Any]:
    pointer_exists, value = resolve_json_pointer(document, clause.pointer)
    result: dict[str, Any] = {
        "pointer": clause.pointer,
        "pointer_exists": pointer_exists,
        "mode": "type" if clause.expected_json_type is not None else "predicate",
        "expected_json_type": clause.expected_json_type,
        "predicate": clause.predicate,
        "bound": clause.bound,
        "observed_json_type": None,
        "type_matches": None,
        "measurement_name": None,
        "measurement": None,
        "predicate_matches": None,
        "clause_matches": False,
    }
    if not pointer_exists:
        return result

    if clause.expected_json_type is not None:
        observed_type = json_type_name(value)
        matched = json_type_matches(value, clause.expected_json_type)
        result["observed_json_type"] = observed_type
        result["type_matches"] = matched
        result["clause_matches"] = matched
        return result

    assert clause.predicate is not None
    evaluation = evaluate_json_structural_predicate(
        value,
        predicate=clause.predicate,
        bound=clause.bound,
    )
    for key in (
        "expected_json_type",
        "observed_json_type",
        "type_matches",
        "measurement_name",
        "measurement",
        "predicate_matches",
    ):
        result[key] = evaluation[key]
    result["clause_matches"] = bool(
        evaluation["type_matches"] and evaluation["predicate_matches"]
    )
    return result
