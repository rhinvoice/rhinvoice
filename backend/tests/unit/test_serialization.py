from rhinvoice.domain.document.document import IssueSnapshot
from rhinvoice.infrastructure.db.serialization import snapshot_from_json, snapshot_to_json
from tests.unit.domain import factories


def test_snapshots_keep_the_notice_and_older_ones_have_none() -> None:
    snapshot = IssueSnapshot(
        company=factories.company(),
        customer=factories.customer(),
        bank_account=factories.bank_account(),
        notice="Reverse Charge.",
        goods_notice="Innergemeinschaftliche Lieferung.",
    )
    data = snapshot_to_json(snapshot)
    assert data["notice"] == "Reverse Charge."
    assert data["goods_notice"] == "Innergemeinschaftliche Lieferung."
    assert snapshot_from_json(data) == snapshot
    # Snapshots written before version 0.4 have no "notice" key, before 0.6 no goods notice.
    del data["notice"]
    del data["goods_notice"]
    assert snapshot_from_json(data).notice is None
    assert snapshot_from_json(data).goods_notice is None


def test_snapshots_keep_the_buyer_reference_and_older_ones_have_none() -> None:
    snapshot = IssueSnapshot(
        company=factories.company(),
        customer=factories.customer(buyer_reference="04011000-1234512345-06"),
        bank_account=None,
    )
    data = snapshot_to_json(snapshot)
    assert data["customer"]["buyer_reference"] == "04011000-1234512345-06"
    assert snapshot_from_json(data) == snapshot
    # Customers frozen before version 0.8 have no buyer reference.
    del data["customer"]["buyer_reference"]
    assert snapshot_from_json(data).customer.buyer_reference == ""
