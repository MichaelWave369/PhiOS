from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from phios.mandala import OriginKind

from .config import MemoryRuntimeConfig, write_disabled_template
from .legacy import plan_legacy_agent_memory_import
from .history_projection_server import DEFAULT_HISTORY_PORT, serve_system_history
from .models import MemoryRecord
from .operator import MemoryOperatorRuntime
from .system_history import SystemHistoryPersistenceBridge

DEFAULT_CONFIG = Path.home() / ".phios" / "memory" / "config.json"
DEFAULT_STATE_ROOT = Path.home() / ".phios" / "memory"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phi-memory",
        description="PhiOS governed memory operator surface",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    parser.add_argument("--allow", action="append", default=[], metavar="PERMISSION")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-config", help="Write a disabled governed-memory config template")
    init.add_argument("--overwrite", action="store_true")

    sub.add_parser("status", help="Show configured governed-memory state")

    put = sub.add_parser("put", help="Store one governed canonical memory record")
    put.add_argument("--record-id", required=True)
    put.add_argument("--revision", type=int, default=1)
    put.add_argument("--source-id", required=True)
    put.add_argument("--source-kind", choices=[item.value for item in OriginKind], required=True)
    put.add_argument("--provenance-ref", action="append", default=[])
    put.add_argument("--scope", required=True)
    put.add_argument("--classification", required=True)
    put.add_argument("--expires-at")
    put.add_argument("--epistemic-kind", choices=["source", "derived"], default="source")
    put.add_argument("--derived-from", action="append", default=[])
    put.add_argument("--contradicts", action="append", default=[])
    put.add_argument("--text", required=True)
    put.add_argument("--operation-id")

    get = sub.add_parser("get", help="Read one governed canonical record by ID")
    get.add_argument("record_id")

    search = sub.add_parser("search", help="Run governed local semantic retrieval")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--operation-id")

    delete = sub.add_parser("delete", help="Tombstone one governed memory record")
    delete.add_argument("record_id")
    delete.add_argument("--operation-id")

    reindex = sub.add_parser("reindex", help="Process explicit derived-index maintenance")
    reindex.add_argument("--full", action="store_true")
    reindex.add_argument("--limit", type=int, default=100)

    legacy = sub.add_parser(
        "legacy-import",
        help="Explicitly import one legacy agent-memory narrative JSON file",
    )
    legacy.add_argument("--file", required=True)
    legacy.add_argument("--scope", required=True)
    legacy.add_argument("--classification", required=True)
    legacy.add_argument("--dry-run", action="store_true")

    history = sub.add_parser(
        "persist-system-history",
        help="Persist one governed PhiShell state transition into canonical memory",
    )
    history.add_argument("--previous-state", required=True)
    history.add_argument("--current-state", required=True)
    history.add_argument("--change-receipt", required=True)

    history_read = sub.add_parser(
        "serve-system-history",
        help="Serve bounded governed persistent history over loopback-only HTTP",
    )
    history_read.add_argument("--port", type=int, default=DEFAULT_HISTORY_PORT)

    return parser


def _runtime(args: argparse.Namespace) -> MemoryOperatorRuntime:
    config = MemoryRuntimeConfig.load(Path(args.config))
    return MemoryOperatorRuntime(
        state_root=Path(args.state_root),
        config=config,
        allowed_permissions=tuple(dict.fromkeys(args.allow)),
    )


def _task_id() -> str:
    return f"memory-cli:{uuid.uuid4()}"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config)

    if args.command == "init-config":
        try:
            write_disabled_template(config_path, overwrite=args.overwrite)
        except FileExistsError:
            parser.error(f"config already exists: {config_path}")
        print(json.dumps({"created": str(config_path.expanduser()), "enabled": False}, indent=2))
        return 0

    try:
        runtime = _runtime(args)

        if args.command == "status":
            print(json.dumps(runtime.status().to_dict(), indent=2))
            return 0

        if args.command == "put":
            if args.epistemic_kind == "derived":
                raise ValueError(
                    "direct derived memory writes require verified transformation lineage; "
                    "use a lineage-producing importer or subsystem"
                )
            record = MemoryRecord.build(
                record_id=args.record_id,
                revision=args.revision,
                source_id=args.source_id,
                source_kind=args.source_kind,
                provenance_refs=tuple(args.provenance_ref),
                created_at=datetime.now(UTC).isoformat(),
                scope_id=args.scope,
                classification=args.classification,
                retention_policy_id=runtime.config.retention_policy_id,
                expires_at=args.expires_at,
                epistemic_kind=args.epistemic_kind,
                derived_from=tuple(args.derived_from),
                contradicts=tuple(args.contradicts),
                text=args.text,
            )
            result = runtime.put(
                record,
                operation_id=args.operation_id or str(uuid.uuid4()),
                task_id=_task_id(),
            )
            print(json.dumps(_result_dict(result), indent=2))
            return 0 if result.status == "ok" else 2

        if args.command == "get":
            result = runtime.get(args.record_id, task_id=_task_id())
            print(json.dumps(_result_dict(result), indent=2))
            return 0 if result.status == "ok" else 2

        if args.command == "search":
            result = runtime.semantic_search(
                args.query,
                operation_id=args.operation_id or str(uuid.uuid4()),
                task_id=_task_id(),
                limit=args.limit,
            )
            print(json.dumps(_result_dict(result), indent=2))
            return 0 if result.status == "ok" else 2

        if args.command == "delete":
            result = runtime.delete(
                args.record_id,
                operation_id=args.operation_id or str(uuid.uuid4()),
                task_id=_task_id(),
            )
            print(json.dumps(_result_dict(result), indent=2))
            return 0 if result.status == "ok" else 2

        if args.command == "reindex":
            reindex_result = runtime.reindex(full=args.full, limit=args.limit)
            print(json.dumps(reindex_result.__dict__, indent=2))
            return 0 if reindex_result.status == "ok" else 2

        if args.command == "serve-system-history":
            serve_system_history(runtime, port=args.port)
            return 0

        if args.command == "persist-system-history":
            previous_state = _load_json_object(Path(args.previous_state))
            current_state = _load_json_object(Path(args.current_state))
            change_receipt = _load_json_object(Path(args.change_receipt))
            persisted = SystemHistoryPersistenceBridge(runtime).persist_transition(
                previous_state=previous_state,
                current_state=current_state,
                change_receipt=change_receipt,
                task_id=_task_id(),
            )
            print(
                json.dumps(
                    {
                        "persistent": persisted.persistent,
                        "canonical": persisted.canonical,
                        "state_record_ids": list(persisted.state_record_ids),
                        "change_record_id": persisted.change_record_id,
                        "state_receipt_ids": list(persisted.state_receipt_ids),
                        "change_receipt_id": persisted.change_receipt_id,
                        "operational_authority": persisted.operational_authority,
                        "action_authority": persisted.action_authority,
                        "execution_authority": persisted.execution_authority,
                    },
                    indent=2,
                )
            )
            return 0

        if args.command == "legacy-import":
            plan = plan_legacy_agent_memory_import(
                Path(args.file),
                scope_id=args.scope,
                classification=args.classification,
                retention_policy_id=runtime.config.retention_policy_id,
            )
            if args.dry_run:
                print(
                    json.dumps(
                        {
                            "source_path": plan.source_path,
                            "source_sha256": plan.source_sha256,
                            "count": plan.count,
                            "record_ids": [item.record.record_id for item in plan.items],
                            "dry_run": True,
                        },
                        indent=2,
                    )
                )
                return 0
            imported, record_ids = runtime.import_legacy(plan, task_id=_task_id())
            print(
                json.dumps(
                    {
                        "source_path": plan.source_path,
                        "source_sha256": plan.source_sha256,
                        "imported": imported,
                        "record_ids": list(record_ids),
                    },
                    indent=2,
                )
            )
            return 0

    except (ValueError, RuntimeError, PermissionError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    parser.error("unknown memory command")
    return 2


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"history input does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"history input is invalid JSON: {path}: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"history input must be a JSON object: {path}")
    return raw


def _result_dict(result: object) -> dict[str, object]:
    from .models import MemoryResult

    if not isinstance(result, MemoryResult):
        raise TypeError("expected MemoryResult")
    return {
        "status": result.status,
        "record": result.record.to_dict() if result.record is not None else None,
        "hits": [
            {
                "record": hit.record.to_dict(),
                "retrieval_distance": hit.retrieval_distance,
            }
            for hit in result.hits
        ],
        "receipt_id": result.receipt_id,
        "error_code": result.error_code,
    }


if __name__ == "__main__":
    raise SystemExit(main())
