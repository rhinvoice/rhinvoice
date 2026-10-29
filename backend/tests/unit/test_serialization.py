from decimal import Decimal

from rhinvoice.domain.document.document import IssueSnapshot
from rhinvoice.domain.document.lines import DocumentLine, LineKind, PriceMode
from rhinvoice.domain.recurring.plan import InvoiceTemplate
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.db.serialization import (
    snapshot_from_json,
    snapshot_to_json,
    template_from_json,
    template_to_json,
)
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


def test_snapshots_keep_a_third_party_and_older_accounts_are_own_ones() -> None:
    provider = factories.bank_account(
        holder="Inkasso AG", third_party=True, holder_address=factories.address(city="Basel")
    )
    own = factories.bank_account()
    snapshot = IssueSnapshot(
        company=factories.company(),
        customer=factories.customer(),
        bank_account=provider,
        accounts=(own, provider),
    )
    data = snapshot_to_json(snapshot)
    assert data["bank_account"]["third_party"] is True
    assert data["bank_account"]["holder_address"]["city"] == "Basel"
    assert snapshot_from_json(data) == snapshot
    # Accounts frozen before version 0.9 have neither key.
    del data["bank_account"]["third_party"]
    del data["bank_account"]["holder_address"]
    older = snapshot_from_json(data).bank_account
    assert older is not None
    assert (older.third_party, older.holder_address) == (False, None)


def test_plan_templates_keep_the_account_and_older_ones_name_none() -> None:
    line = DocumentLine(
        id=new_id(),
        kind=LineKind.ITEM,
        description="Hosting",
        quantity=Decimal(1),
        unit=None,
        unit_price=Decimal(29),
    )
    account_id = new_id()
    template = InvoiceTemplate(
        currency=Currency.CHF,
        price_mode=PriceMode.NET,
        lines=(line,),
        bank_account_id=account_id,
    )
    data = template_to_json(template)
    assert data["bank_account_id"] == str(account_id)
    assert template_from_json(data) == template
    del data["bank_account_id"]
    assert template_from_json(data).bank_account_id is None
