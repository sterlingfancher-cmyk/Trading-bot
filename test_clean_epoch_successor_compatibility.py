import types

import clean_epoch_successor_compatibility as compat


def _core(epoch):
    core = types.SimpleNamespace()
    core.portfolio = {"paper_accounting_epoch": epoch}
    return core


def test_exact_verified_successor_is_recognized():
    core = _core({
        "id": compat.NEW_EPOCH_ID,
        "prior_epoch_id": compat.OLD_EPOCH_ID,
        "historical_recovery_decision": "verified_snapshot_rollforward",
        "historical_evidence_archived": True,
    })
    assert compat._is_verified_successor(core) is True


def test_unrelated_epoch_is_not_recognized():
    core = _core({
        "id": "some-other-epoch",
        "prior_epoch_id": compat.OLD_EPOCH_ID,
        "historical_recovery_decision": "verified_snapshot_rollforward",
        "historical_evidence_archived": True,
    })
    assert compat._is_verified_successor(core) is False
