from __future__ import annotations

from dataclasses import dataclass

QUERY_CATALOG_VERSION = "phios.ledger_reports.query_catalog.v0.1"
MAX_REPORT_ROWS = 1000


@dataclass(frozen=True, kw_only=True)
class NamedQuery:
    name: str
    sql: str
    description: str


_QUERY_LIST = (
    NamedQuery(
        name="execution_outcomes_v1",
        description="Counts execution outcomes by capability and permission status.",
        sql="""
            SELECT
                capability_id,
                permission_status,
                execution_status,
                COUNT(*)::BIGINT AS receipt_count
            FROM execution_receipts
            GROUP BY capability_id, permission_status, execution_status
            ORDER BY receipt_count DESC, capability_id, permission_status, execution_status
            LIMIT ?
        """,
    ),
    NamedQuery(
        name="permission_denials_v1",
        description="Counts denied execution requests without exposing raw payloads.",
        sql="""
            SELECT
                capability_id,
                permissions_requested_json,
                COUNT(*)::BIGINT AS denial_count
            FROM execution_receipts
            WHERE permission_status = 'denied'
            GROUP BY capability_id, permissions_requested_json
            ORDER BY denial_count DESC, capability_id, permissions_requested_json
            LIMIT ?
        """,
    ),
    NamedQuery(
        name="repeated_failures_v1",
        description="Shows capability/planner pairs with at least two failed executions.",
        sql="""
            SELECT
                capability_id,
                planner,
                COUNT(*)::BIGINT AS failure_count
            FROM execution_receipts
            WHERE execution_status = 'failed'
            GROUP BY capability_id, planner
            HAVING COUNT(*) >= 2
            ORDER BY failure_count DESC, capability_id, planner
            LIMIT ?
        """,
    ),
    NamedQuery(
        name="lineage_v1",
        description="Lists missing receipt links without inventing lineage.",
        sql="""
            SELECT link_kind, source_receipt_id, missing_receipt_id
            FROM (
                SELECT
                    'execution_gate' AS link_kind,
                    e.receipt_id AS source_receipt_id,
                    e.gate_receipt_id AS missing_receipt_id
                FROM execution_receipts e
                LEFT JOIN mandala_receipts m ON m.receipt_id = e.gate_receipt_id
                WHERE e.gate_receipt_id IS NOT NULL AND m.receipt_id IS NULL

                UNION ALL

                SELECT
                    'execution_action' AS link_kind,
                    e.receipt_id AS source_receipt_id,
                    e.action_receipt_id AS missing_receipt_id
                FROM execution_receipts e
                LEFT JOIN mandala_receipts m ON m.receipt_id = e.action_receipt_id
                WHERE e.action_receipt_id IS NOT NULL AND m.receipt_id IS NULL

                UNION ALL

                SELECT
                    'mandala_parent' AS link_kind,
                    m.receipt_id AS source_receipt_id,
                    m.parent_receipt_id AS missing_receipt_id
                FROM mandala_receipts m
                LEFT JOIN mandala_receipts p ON p.receipt_id = m.parent_receipt_id
                WHERE m.parent_receipt_id IS NOT NULL AND p.receipt_id IS NULL
            )
            ORDER BY link_kind, source_receipt_id, missing_receipt_id
            LIMIT ?
        """,
    ),
    NamedQuery(
        name="coverage_v1",
        description="Reports snapshot row counts and lineage coverage state.",
        sql="""
            SELECT
                snapshot_id,
                execution_rows,
                mandala_rows,
                coverage_complete,
                missing_execution_links,
                dangling_parent_receipts
            FROM projection_metadata
            LIMIT ?
        """,
    ),
)

QUERY_CATALOG = {item.name: item for item in _QUERY_LIST}


def get_named_query(name: str) -> NamedQuery:
    try:
        return QUERY_CATALOG[name]
    except KeyError as exc:
        raise ValueError(f"unknown Ledger report name: {name}") from exc


def list_named_queries() -> tuple[NamedQuery, ...]:
    return _QUERY_LIST
