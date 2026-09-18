from pathlib import Path

from phios.mandala import MandalaStatus
from phios.soma import OcrEngineError, OcrEngineResult, OcrSpec, PNG_SIGNATURE
from phios.spine.runtime import PhiOSSpine


class FakeOcrProvider:
    name = "fake-ocr"

    def __init__(
        self,
        *,
        result: OcrEngineResult | None = None,
        error: OcrEngineError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def read(self, data: bytes, *, spec: OcrSpec) -> OcrEngineResult:
        self.calls += 1
        assert data.startswith(PNG_SIGNATURE)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _image_source(spine: PhiOSSpine) -> str:
    evidence = spine.soma.evidence.put_bytes(
        PNG_SIGNATURE + b"fake-image",
        media_type="image/png",
        suffix=".png",
    )
    return evidence.evidence_ref


def _result(
    text: str = "HELLO 369",
    *,
    confidences: tuple[float, ...] = (91.0, 87.0),
) -> OcrEngineResult:
    return OcrEngineResult(
        text=text,
        confidences=confidences,
        engine="fake-engine",
        engine_version="1.2.3",
        width=320,
        height=200,
    )


def test_ocr_requires_explicit_grant(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, task_id="ocr-denied")
    ref = _image_source(spine)
    provider = FakeOcrProvider(result=_result())

    result = spine.ocr_screen_evidence(
        evidence_ref=ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert result.text_evidence is None
    assert "missing_grant:perception.ocr.read" in result.receipt.limitations


def test_ocr_creates_separate_text_evidence_and_receipt(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-ok",
    )
    ref = _image_source(spine)
    source_before = spine.soma.evidence.read_bytes(ref)
    provider = FakeOcrProvider(result=_result())

    result = spine.ocr_screen_evidence(
        evidence_ref=ref,
        provider=provider,
        spec=OcrSpec(language="eng", page_segmentation_mode=6),
    )

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert result.text == "HELLO 369"
    assert result.text_evidence is not None
    assert Path(result.text_evidence.path).read_text(encoding="utf-8") == "HELLO 369"
    assert spine.soma.evidence.read_bytes(ref) == source_before
    assert result.receipt.source_evidence_ref == ref
    assert result.receipt.output_evidence_ref == result.text_evidence.evidence_ref
    assert result.receipt.engine == "fake-engine"
    assert result.receipt.engine_version == "1.2.3"
    assert result.receipt.confidence_mean == 89.0
    assert result.receipt.character_count == 9
    assert result.receipt.token_count == 2

    receipts = spine.mandala_ledger.recent(2)
    assert receipts[0]["receipt_type"] == "GateReceipt"
    assert receipts[1]["receipt_type"] == "OcrReceipt"


def test_ocr_result_hides_text_by_default(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-hide-text",
    )
    ref = _image_source(spine)
    provider = FakeOcrProvider(result=_result("PRIVATE TEXT"))

    result = spine.ocr_screen_evidence(evidence_ref=ref, provider=provider)

    assert "text" not in result.to_dict()
    assert result.to_dict(include_text=True)["text"] == "PRIVATE TEXT"


def test_no_text_detected_is_degraded_not_invented(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-empty",
    )
    ref = _image_source(spine)
    provider = FakeOcrProvider(result=_result("   ", confidences=()))

    result = spine.ocr_screen_evidence(evidence_ref=ref, provider=provider)

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.text == ""
    assert result.text_evidence is None
    assert "no_text_detected" in result.receipt.limitations


def test_text_without_confidence_is_degraded(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-no-confidence",
    )
    ref = _image_source(spine)
    provider = FakeOcrProvider(result=_result("maybe text", confidences=()))

    result = spine.ocr_screen_evidence(evidence_ref=ref, provider=provider)

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.text_evidence is not None
    assert result.receipt.confidence_mean is None
    assert "confidence_unavailable" in result.receipt.limitations


def test_invalid_language_is_blocked_before_provider(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-language",
    )
    ref = _image_source(spine)
    provider = FakeOcrProvider(result=_result())

    result = spine.ocr_screen_evidence(
        evidence_ref=ref,
        provider=provider,
        spec=OcrSpec(language="eng;rm -rf"),
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "invalid_ocr_language" in result.receipt.limitations


def test_non_png_evidence_is_blocked(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-media",
    )
    evidence = spine.soma.evidence.put_text("not an image")
    provider = FakeOcrProvider(result=_result())

    result = spine.ocr_screen_evidence(
        evidence_ref=evidence.evidence_ref,
        provider=provider,
    )

    assert result.receipt.status is MandalaStatus.BLOCKED
    assert provider.calls == 0
    assert "unsupported_ocr_media" in result.receipt.limitations


def test_engine_unavailable_is_degraded(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-engine-missing",
    )
    ref = _image_source(spine)
    provider = FakeOcrProvider(
        error=OcrEngineError("ocr_engine_unavailable", "missing engine")
    )

    result = spine.ocr_screen_evidence(evidence_ref=ref, provider=provider)

    assert result.receipt.status is MandalaStatus.DEGRADED
    assert result.text_evidence is None
    assert "no_symbolic_interpretation_promoted" in result.receipt.limitations


def test_engine_failure_is_quarantined(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-engine-failure",
    )
    ref = _image_source(spine)
    provider = FakeOcrProvider(
        error=OcrEngineError("ocr_engine_failed", "failed")
    )

    result = spine.ocr_screen_evidence(evidence_ref=ref, provider=provider)

    assert result.receipt.status is MandalaStatus.QUARANTINED
    assert result.text_evidence is None


def test_ocr_does_not_expand_authority(tmp_path: Path) -> None:
    spine = PhiOSSpine(
        state_root=tmp_path,
        allowed_permissions=["perception.ocr.read"],
        task_id="ocr-authority",
    )
    ref = _image_source(spine)
    before = spine.core.authority
    provider = FakeOcrProvider(result=_result())

    result = spine.ocr_screen_evidence(evidence_ref=ref, provider=provider)

    assert result.receipt.status is MandalaStatus.ACCEPTED
    assert spine.core.authority == before
    assert result.packet.authority == before
