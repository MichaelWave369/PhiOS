from __future__ import annotations

from phios.core.geometric_reasoning import (
    ConstraintSpec,
    GeometricReasoner,
    InvariantSpec,
)


def _pair_id(state: tuple[int, int]) -> str:
    return f"{state[0]},{state[1]}"


def test_reduce_quotients_symmetric_states_and_prunes_invalid_region():
    reasoner = GeometricReasoner(
        state_id=_pair_id,
        equivalence_key=lambda state: sorted(state),
        constraints=(
            ConstraintSpec("sum_lte_3", lambda state: sum(state) <= 3),
        ),
    )

    receipt = reasoner.reduce([(0, 1), (1, 0), (1, 1), (4, 0)])

    assert receipt.raw_state_count == 4
    assert receipt.admissible_state_count == 3
    assert receipt.rejected_state_count == 1
    assert receipt.quotient_class_count == 2
    assert receipt.action_authority is False
    assert receipt.rejections == (("4,0", ("sum_lte_3",)),)
    assert sorted(item.member_ids for item in receipt.classes) == [
        ("0,1", "1,0"),
        ("1,1",),
    ]


def test_invariant_mismatch_proves_unreachable_only_under_declared_conservation():
    reasoner = GeometricReasoner(
        state_id=_pair_id,
        equivalence_key=lambda state: sorted(state),
        invariants=(
            InvariantSpec(
                "parity",
                lambda state: sum(state) % 2,
                conserved=True,
            ),
            InvariantSpec(
                "orientation",
                lambda state: state[0] <= state[1],
                conserved=False,
            ),
        ),
    )

    receipt = reasoner.compare_invariants((0, 0), (1, 0))

    assert receipt.status == "unreachable_under_conserved_invariants"
    assert receipt.mismatched_conserved_invariants == ("parity",)
    assert receipt.action_authority is False


def test_search_visits_one_representative_per_equivalence_class():
    reasoner = GeometricReasoner(
        state_id=_pair_id,
        equivalence_key=lambda state: sorted(state),
        constraints=(
            ConstraintSpec("sum_lte_4", lambda state: sum(state) <= 4),
        ),
        quotient_search_safe=True,
    )

    def expand(state: tuple[int, int]):
        a, b = state
        return [(a + 1, b), (a, b + 1)]

    receipt = reasoner.search(
        [(0, 0)],
        expand=expand,
        goal=lambda state: sum(state) == 3 and min(state) >= 1,
    )

    assert receipt.status == "found"
    assert receipt.solution_id in {"1,2", "2,1"}
    assert receipt.raw_states_seen > receipt.quotient_classes_visited
    assert receipt.equivalent_states_skipped >= 1
    assert receipt.representative_path_ids[0] == "0,0"
    assert receipt.action_authority is False


def test_receipts_are_deterministic_for_same_reduction():
    reasoner = GeometricReasoner(
        state_id=_pair_id,
        equivalence_key=lambda state: sorted(state),
    )

    first = reasoner.reduce([(1, 0), (0, 1), (1, 1)])
    second = reasoner.reduce([(1, 1), (0, 1), (1, 0)])

    assert first.receipt_sha256 == second.receipt_sha256
    assert first.to_dict() == second.to_dict()


def test_constraint_exception_fails_closed_as_rejection():
    reasoner = GeometricReasoner(
        state_id=_pair_id,
        equivalence_key=lambda state: sorted(state),
        constraints=(
            ConstraintSpec(
                "fragile_constraint",
                lambda state: (_ for _ in ()).throw(
                    RuntimeError("boom")
                )
                if state == (9, 9)
                else True,
            ),
        ),
    )

    receipt = reasoner.reduce([(0, 0), (9, 9)])

    assert receipt.admissible_state_count == 1
    assert receipt.rejections == (("9,9", ("fragile_constraint",)),)


def test_search_refuses_undeclared_quotient_safety():
    reasoner = GeometricReasoner(
        state_id=_pair_id,
        equivalence_key=lambda state: sorted(state),
    )

    try:
        reasoner.search(
            [(0, 0)],
            expand=lambda state: [state],
            goal=lambda state: False,
        )
    except Exception as exc:
        assert "quotient_search_safe=True" in str(exc)
    else:
        raise AssertionError("search should require explicit quotient-safety declaration")
