from architecture_debt_regression_gate import evaluate


def _report(**deltas):
    return {
        "comparison": {
            "base_available": True,
            "summary_delta": deltas,
            "new_warnings": [],
        }
    }


def test_existing_debt_with_no_positive_delta_passes():
    result = evaluate(
        _report(
            mutation_overlaps=0,
            broad_exception_passes=-2,
            warning_findings=-1,
            info_findings=0,
        )
    )
    assert result["status"] == "pass"
    assert result["enforced"] is True


def test_new_mutation_overlap_fails():
    result = evaluate(_report(mutation_overlaps=1))
    assert result["status"] == "fail"
    assert {row["metric"] for row in result["violations"]} == {"mutation_overlaps"}


def test_new_suppressed_exception_fails():
    result = evaluate(_report(broad_exception_passes=1))
    assert result["status"] == "fail"
    assert result["violations"][0]["metric"] == "broad_exception_passes"


def test_new_info_debt_fails_without_reclassifying_existing_findings():
    result = evaluate(_report(info_findings=1))
    assert result["status"] == "fail"
    assert result["policy"]["existing_debt_is_not_failed"] is True


def test_scheduled_full_audit_without_base_is_observational():
    result = evaluate({"comparison": {"base_available": False, "summary_delta": {}}})
    assert result["status"] == "pass"
    assert result["enforced"] is False
