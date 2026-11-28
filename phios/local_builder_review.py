"""Local Builder R0.4: review restricted expression repairs without executing code."""

import argparse
import ast
import hashlib
import itertools
import json
from pathlib import Path

MAX_INPUT = 64 * 1024
MAX_EXPRESSION = 256
MAX_NODES = 40

TASKS = (
    {
        "id": "port_bounds",
        "parameters": ("port",),
        "buggy": "0 <= port < 65535",
        "requirement": "Return True exactly for integer ports 1 through 65535 inclusive.",
        "domain": ((-2, -1, 0, 1, 2, 80, 443, 65534, 65535, 65536, 65537),),
    },
    {
        "id": "byte_budget",
        "parameters": ("used", "requested", "limit"),
        "buggy": "used + requested < limit",
        "requirement": "Return True only if all three integers are nonnegative and used + requested is at most limit.",
        "domain": ((-1, 0, 1, 2, 8, 9), (-1, 0, 1, 2, 8, 9), (-1, 0, 1, 2, 8, 9)),
    },
    {
        "id": "retry_limit",
        "parameters": ("attempts", "limit"),
        "buggy": "attempts <= limit",
        "requirement": "Return True only if both integers are nonnegative and attempts is strictly less than limit.",
        "domain": ((-1, 0, 1, 2, 3, 8), (-1, 0, 1, 2, 3, 8)),
    },
)


def expected(task_id, args):
    if task_id == "port_bounds":
        return 1 <= args[0] <= 65535
    if task_id == "byte_budget":
        used, requested, limit = args
        return used >= 0 and requested >= 0 and limit >= 0 and used + requested <= limit
    if task_id == "retry_limit":
        attempts, limit = args
        return attempts >= 0 and limit >= 0 and attempts < limit
    raise ValueError("unknown task")


def suite():
    return {
        "schema": "phios.local-builder.tasks.r04",
        "instruction": (
            "Repair each buggy return expression. Return a single JSON object with "
            "schema phios.local-builder.candidate.r04 and repairs, a list of objects "
            "each containing id and expression. Use only parameter names, integer "
            "constants from -65536 through 65536, addition, subtraction, comparisons, "
            "and/or/not, and parentheses. No calls, attributes, indexing, or other Python syntax."
        ),
        "tasks": [
            {key: list(value) if key == "parameters" else value
             for key, value in task.items() if key != "domain"}
            for task in TASKS
        ],
    }


def parse(expression, names):
    if not isinstance(expression, str) or not 0 < len(expression) <= MAX_EXPRESSION:
        raise ValueError("invalid expression length")
    try:
        root = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid expression syntax") from exc
    nodes = list(ast.walk(root))
    if len(nodes) > MAX_NODES:
        raise ValueError("expression too complex")
    allowed = (
        ast.Expression, ast.Name, ast.Load, ast.Constant, ast.BoolOp, ast.And,
        ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.BinOp, ast.Add, ast.Sub,
        ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    )
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError("unsupported expression syntax")
        if isinstance(node, ast.Name) and node.id not in names:
            raise ValueError("unknown parameter")
        if isinstance(node, ast.Constant) and (
            type(node.value) is not int or not 0 <= node.value <= 65536
        ):
            raise ValueError("invalid constant")
    return root.body


def integer(value):
    if type(value) is not int or abs(value) > 2**31:
        raise ValueError("invalid integer intermediate")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError("boolean required")
    return value


def interpret(node, values):
    """Interpret only the validated grammar; never compile or eval a candidate."""
    if isinstance(node, ast.Name):
        return integer(values[node.id])
    if isinstance(node, ast.Constant):
        return integer(node.value)
    if isinstance(node, ast.UnaryOp):
        operand = interpret(node.operand, values)
        if isinstance(node.op, ast.Not):
            return not boolean(operand)
        return integer(-integer(operand))
    if isinstance(node, ast.BinOp):
        left = integer(interpret(node.left, values))
        right = integer(interpret(node.right, values))
        return integer(left + right if isinstance(node.op, ast.Add) else left - right)
    if isinstance(node, ast.BoolOp):
        items = [boolean(interpret(item, values)) for item in node.values]
        return all(items) if isinstance(node.op, ast.And) else any(items)
    if isinstance(node, ast.Compare):
        left = integer(interpret(node.left, values))
        checks = []
        for op, comparator in zip(node.ops, node.comparators):
            right = integer(interpret(comparator, values))
            if isinstance(op, ast.Eq):
                checks.append(left == right)
            elif isinstance(op, ast.NotEq):
                checks.append(left != right)
            elif isinstance(op, ast.Lt):
                checks.append(left < right)
            elif isinstance(op, ast.LtE):
                checks.append(left <= right)
            elif isinstance(op, ast.Gt):
                checks.append(left > right)
            else:
                checks.append(left >= right)
            left = right
        return all(checks)
    raise ValueError("unsupported expression")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def review(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_INPUT:
        raise ValueError("invalid candidate size")
    candidate = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if (not isinstance(candidate, dict) or set(candidate) != {"schema", "repairs"}
            or candidate["schema"] != "phios.local-builder.candidate.r04"
            or not isinstance(candidate["repairs"], list)
            or len(candidate["repairs"]) != len(TASKS)):
        raise ValueError("invalid candidate envelope")
    repairs = {}
    for row in candidate["repairs"]:
        if (not isinstance(row, dict) or set(row) != {"id", "expression"}
                or not isinstance(row["id"], str) or row["id"] in repairs):
            raise ValueError("invalid repair entry")
        repairs[row["id"]] = row["expression"]
    if set(repairs) != {task["id"] for task in TASKS}:
        raise ValueError("incorrect task IDs")
    results = []
    for task in TASKS:
        task_id = task["id"]
        tree = parse(repairs[task_id], task["parameters"])
        passed = total = 0
        for args in itertools.product(*task["domain"]):
            observed = boolean(interpret(tree, dict(zip(task["parameters"], args))))
            passed += int(observed == expected(task_id, args))
            total += 1
        results.append({"id": task_id, "passed": passed, "total": total})
    all_pass = all(row["passed"] == row["total"] for row in results)
    return {
        "schema": "phios.local-builder.review.r04",
        "status": "FIXTURE_MATCH_REVIEW_ONLY" if all_pass else "FIXTURE_MISMATCH",
        "candidate_sha256": hashlib.sha256(raw).hexdigest(),
        "tasks": results,
        "general_correctness_verified": False,
        "model_origin_verified": False,
        "candidate_code_executed": False,
        "repository_modified": False,
        "authority_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("suite")
    inspect = sub.add_parser("review")
    inspect.add_argument("--candidate", required=True)
    args = parser.parse_args()
    if args.command == "suite":
        print(json.dumps(suite(), indent=2))
        return 0
    try:
        with Path(args.candidate).open("rb") as stream:
            result = review(stream.read(MAX_INPUT + 1))
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"status": "INVALID_CANDIDATE"}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "FIXTURE_MATCH_REVIEW_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
