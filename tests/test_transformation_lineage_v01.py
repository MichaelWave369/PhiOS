from dataclasses import replace

import pytest

from phios.mandala import (
    ExactnessClass,
    TransformationLineageBuilder,
    TransformationLineageError,
)


def test_byte_exact_requires_identical_digest() -> None:
    builder = TransformationLineageBuilder()

    receipt = builder.build(
        transform_id="copy",
        transform_version="v1",
        source_refs=("source:a",),
        source_sha256s=("a" * 64,),
        output_ref="output:a",
        output_sha256="a" * 64,
        parameters={},
        requested_exactness=ExactnessClass.BYTE_EXACT,
    )

    assert receipt.exactness_class is ExactnessClass.BYTE_EXACT
    assert receipt.information_loss_possible is False
    assert receipt.semantic_inference is False
    assert receipt.operational_authority is False
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    builder.validate(receipt)

    with pytest.raises(TransformationLineageError, match="identical"):
        builder.build(
            transform_id="copy",
            transform_version="v1",
            source_refs=("source:a",),
            source_sha256s=("a" * 64,),
            output_ref="output:b",
            output_sha256="b" * 64,
            parameters={},
            requested_exactness=ExactnessClass.BYTE_EXACT,
        )


def test_parent_exactness_cannot_be_upgraded_and_taints_propagate() -> None:
    builder = TransformationLineageBuilder()
    parent = builder.build(
        transform_id="crop",
        transform_version="v1",
        source_refs=("source:image",),
        source_sha256s=("a" * 64,),
        output_ref="derived:crop",
        output_sha256="b" * 64,
        parameters={"crop": [0, 0, 10, 10]},
        requested_exactness=ExactnessClass.LOSSY_DERIVED,
        added_taints=("cropped_context",),
        information_loss_possible=True,
    )
    child = builder.build(
        transform_id="copy-after-crop",
        transform_version="v1",
        source_refs=("derived:crop",),
        source_sha256s=("b" * 64,),
        output_ref="derived:copy",
        output_sha256="b" * 64,
        parameters={},
        requested_exactness=ExactnessClass.BYTE_EXACT,
        parent_receipts=(parent,),
    )

    assert child.requested_exactness is ExactnessClass.BYTE_EXACT
    assert child.exactness_class is ExactnessClass.LOSSY_DERIVED
    assert child.effective_taints == ("cropped_context",)
    assert child.parent_receipt_sha256s == (parent.receipt_sha256,)


def test_interpretive_lineage_requires_semantic_inference() -> None:
    builder = TransformationLineageBuilder()

    with pytest.raises(TransformationLineageError, match="semantic inference"):
        builder.build(
            transform_id="ocr",
            transform_version="v1",
            source_refs=("source:image",),
            source_sha256s=("a" * 64,),
            output_ref="derived:text",
            output_sha256="b" * 64,
            parameters={},
            requested_exactness=ExactnessClass.INTERPRETIVE,
            semantic_inference=False,
        )


def test_tampered_receipt_fails_hash_validation() -> None:
    builder = TransformationLineageBuilder()
    receipt = builder.build(
        transform_id="normalize",
        transform_version="v1",
        source_refs=("source:text",),
        source_sha256s=("a" * 64,),
        output_ref="derived:text",
        output_sha256="b" * 64,
        parameters={"newlines": "lf"},
        requested_exactness=ExactnessClass.NORMALIZED,
        added_taints=("normalized_representation",),
        information_loss_possible=True,
    )

    tampered = replace(receipt, effective_taints=())
    with pytest.raises(TransformationLineageError, match="hash"):
        builder.validate(tampered)
