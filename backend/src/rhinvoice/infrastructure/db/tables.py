"""Database schema as SQLAlchemy Core tables.

Domain objects are frozen slotted dataclasses, which the ORM cannot
instrument. Repositories therefore map rows explicitly (see ADR 0002).
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

users = Table(
    "users",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("display_name", String(200), nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("totp_secret", String(64)),
    Column("totp_pending_secret", String(64)),
    Column("failed_logins", Integer, nullable=False, server_default="0"),
    Column("locked_until", DateTime(timezone=True)),
    Column("totp_last_step", BigInteger),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column(
        "user_id",
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)


def _address_columns(prefix: str = "", *, nullable: bool = False) -> list[Column[str]]:
    """Structured address (Swiss QR-bill field lengths)."""
    return [
        Column(
            f"{prefix}street",
            String(70),
            nullable=nullable,
            server_default=None if nullable else "",
        ),
        Column(
            f"{prefix}house_number",
            String(16),
            nullable=nullable,
            server_default=None if nullable else "",
        ),
        Column(
            f"{prefix}supplement",
            String(70),
            nullable=nullable,
            server_default=None if nullable else "",
        ),
        Column(f"{prefix}postal_code", String(16), nullable=nullable),
        Column(f"{prefix}city", String(35), nullable=nullable),
        Column(f"{prefix}country", String(2), nullable=nullable),
    ]


company = Table(
    "company",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("singleton", Boolean, nullable=False, server_default="true", unique=True),
    Column("name", String(70), nullable=False),
    *_address_columns(),
    Column("default_currency", String(3), nullable=False),
    Column("default_language", String(2), nullable=False),
    Column("email", String(254)),
    Column("phone", String(100), nullable=False, server_default=""),
    Column("website", String(100), nullable=False, server_default=""),
    Column("vat_number", String(40)),
    Column("tax_number", String(100), nullable=False, server_default=""),
    Column("commercial_register", String(200), nullable=False, server_default=""),
    Column("small_business", Boolean, nullable=False),
    Column("cash_rounding", Boolean, nullable=False),
    Column("payment_terms_days", SmallInteger, nullable=False),
    Column("accent_hue", SmallInteger, nullable=False),
    # One company per installation (multi-tenancy is prepared via UUIDs, see ADR 0004).
    CheckConstraint("singleton", name="single_row"),
)

company_logo = Table(
    "company_logo",
    metadata,
    Column("singleton", Boolean, primary_key=True, server_default="true"),
    Column("media_type", String(50), nullable=False),
    Column("content", LargeBinary, nullable=False),
    CheckConstraint("singleton", name="single_row"),
)

bank_accounts = Table(
    "bank_accounts",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("currency", String(3), nullable=False),
    Column("bank_name", String(70), nullable=False),
    Column("holder", String(70), nullable=False),
    Column("iban", String(34), nullable=False),
    Column("qr_iban", String(34)),
    Column("bic", String(11)),
    Column("is_default", Boolean, nullable=False),
    # A third party's account (ADR 0037) names the holder's address; own accounts have none.
    Column("third_party", Boolean, nullable=False, server_default="false"),
    *_address_columns("holder_", nullable=True),
    CheckConstraint(
        "NOT third_party OR holder_postal_code IS NOT NULL", name="third_party_address"
    ),
    Index(
        "uq_bank_accounts_default_per_currency",
        "currency",
        unique=True,
        postgresql_where=text("is_default"),
    ),
)

customers = Table(
    "customers",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("number", String(20), nullable=False, unique=True),
    Column("kind", String(10), nullable=False),
    Column("company_name", String(70), nullable=False, server_default=""),
    Column("salutation", String(50), nullable=False, server_default=""),
    Column("first_name", String(50), nullable=False, server_default=""),
    Column("last_name", String(50), nullable=False, server_default=""),
    Column("contact_person", String(70), nullable=False, server_default=""),
    *_address_columns(),
    *_address_columns("delivery_", nullable=True),
    Column("email", String(254)),
    Column("phone", String(50), nullable=False, server_default=""),
    Column("vat_number", String(40)),
    Column("buyer_reference", String(100), nullable=False, server_default=""),
    Column("customer_group", String(50), nullable=False, server_default=""),
    Column("default_currency", String(3)),
    Column("default_language", String(2)),
    Column("tax_exempt", Boolean, nullable=False),
    Column("default_discount", Numeric(5, 2), nullable=False),
    Column("payment_terms_days", SmallInteger),
    Column("note", Text, nullable=False, server_default=""),
    Column("archived", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

articles = Table(
    "articles",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("number", String(30), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("article_group", String(50), nullable=False, server_default=""),
    Column("unit", String(3), nullable=False),
    Column("tax_category", String(10), nullable=False),
    Column("supply", String(10), nullable=False, server_default="service"),
    Column("archived", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

article_prices = Table(
    "article_prices",
    metadata,
    Column(
        "article_id",
        Uuid(),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("currency", String(3), primary_key=True),
    Column("price", Numeric(12, 4), nullable=False),
)

number_sequences = Table(
    "number_sequences",
    metadata,
    Column("kind", String(20), primary_key=True),
    Column("pattern", String(40), nullable=False),
    Column("start_value", BigInteger, nullable=False),
    Column("yearly_reset", Boolean, nullable=False),
    Column("next_value", BigInteger, nullable=False),
    Column("last_year", SmallInteger),
)


documents = Table(
    "documents",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("type", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("number", String(30)),
    Column("customer_id", Uuid(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("language", String(2), nullable=False),
    Column("price_mode", String(10), nullable=False),
    Column("treatment", String(20), nullable=False),
    Column("treatment_overridden", Boolean, nullable=False),
    Column("goods_treatment", String(20)),
    Column("discount_kind", String(10), nullable=False),
    Column("discount_value", Numeric(14, 2), nullable=False),
    Column("issue_date", Date),
    Column("due_date", Date),
    Column("service_from", Date),
    Column("service_to", Date),
    Column("subject", String(200), nullable=False, server_default=""),
    Column("reference", String(100), nullable=False, server_default=""),
    Column("intro_text", Text, nullable=False, server_default=""),
    Column("payment_text", Text, nullable=False, server_default=""),
    Column("closing_text", Text, nullable=False, server_default=""),
    # The account chosen for a draft; issuing freezes the account in the snapshot.
    Column("bank_account_id", Uuid(), ForeignKey("bank_accounts.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("issued_at", DateTime(timezone=True)),
    Column("source_id", Uuid(), ForeignKey("documents.id", ondelete="RESTRICT")),
    Column("cancelled_by_id", Uuid()),
    # Deleting the invoice draft frees the quote for another conversion.
    Column("converted_to_id", Uuid(), ForeignKey("documents.id", ondelete="SET NULL")),
    Column("pdf_sha256", String(64)),
    Column("origin", String(20), nullable=False, server_default="rhinvoice"),
    Column("snapshot", JSONB),
    Column("issued_totals", JSONB),
    # Denormalised values for lists, sorting, search and the dashboard.
    Column("customer_name", String(200), nullable=False, server_default=""),
    Column("net_amount", Numeric(14, 2), nullable=False),
    Column("total_amount", Numeric(14, 2), nullable=False),
    Column("open_amount", Numeric(14, 2), nullable=False),
    Column("written_off_amount", Numeric(14, 2), nullable=False, server_default="0"),
    Column("search_vector", TSVECTOR, nullable=False),
    UniqueConstraint("type", "number", name="uq_documents_type_number"),
    CheckConstraint("(status = 'draft') = (number IS NULL)", name="number_iff_issued"),
    Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
    Index("ix_documents_type_status", "type", "status"),
    Index("ix_documents_customer_id", "customer_id"),
)

document_lines = Table(
    "document_lines",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("document_id", Uuid(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
    Column("position", SmallInteger, nullable=False),
    Column("kind", String(10), nullable=False),
    Column("description", String(500), nullable=False, server_default=""),
    Column("details", Text, nullable=False, server_default=""),
    Column("quantity", Numeric(14, 4), nullable=False),
    Column("unit", String(3)),
    Column("unit_price", Numeric(14, 4), nullable=False),
    Column("discount_percent", Numeric(5, 2), nullable=False),
    Column("tax_category", String(10), nullable=False),
    Column("supply", String(10), nullable=False, server_default="service"),
    Column("tax_rate", Numeric(5, 2)),
    Column("article_id", Uuid(), ForeignKey("articles.id", ondelete="SET NULL")),
    UniqueConstraint("document_id", "position", name="uq_document_lines_document_position"),
)

document_payments = Table(
    "document_payments",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column(
        "document_id",
        Uuid(),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("paid_on", Date, nullable=False),
    Column("amount", Numeric(14, 2), nullable=False),
    Column("note", String(500), nullable=False, server_default=""),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)

# What was open of an invoice when collecting it was given up; at most one per invoice.
document_write_offs = Table(
    "document_write_offs",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column(
        "document_id",
        Uuid(),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("written_off_on", Date, nullable=False),
    Column("amount", Numeric(14, 2), nullable=False),
    Column("reason", String(20), nullable=False),
    Column("note", String(500), nullable=False, server_default=""),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("amount > 0", name="amount_positive"),
)

document_events = Table(
    "document_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column(
        "document_id",
        Uuid(),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("kind", String(30), nullable=False),
    Column("detail", String(500), nullable=False, server_default=""),
)


text_templates = Table(
    "text_templates",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("kind", String(10), nullable=False),
    Column("document_type", String(20), nullable=False),
    Column("language", String(2), nullable=False),
    Column("name", String(70), nullable=False),
    Column("text", Text, nullable=False),
    Column("is_default", Boolean, nullable=False),
    Column("position", Integer, nullable=False),
)

legal_notices = Table(
    "legal_notices",
    metadata,
    Column("treatment", String(20), primary_key=True),
    Column("language", String(2), primary_key=True),
    Column("text", Text, nullable=False),
)

document_pdfs = Table(
    "document_pdfs",
    metadata,
    Column(
        "document_id",
        Uuid(),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("content", LargeBinary, nullable=False),
    Column("e_invoice", LargeBinary),
)

# Further files of issued invoices (reminders, copies of another program); only added.
document_attachments = Table(
    "document_attachments",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column(
        "document_id",
        Uuid(),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    Column("file_name", String(255), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("added_at", DateTime(timezone=True), nullable=False),
)

# Written by the app (requests) and by the backup container (runs, see backup/).
backup_requests = Table(
    "backup_requests",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("reason", String(20), nullable=False),
    Column("handled_at", DateTime(timezone=True), nullable=True),
    CheckConstraint("reason IN ('daily', 'document', 'manual')", name="reason"),
    Index(
        "ix_backup_requests_pending",
        "requested_at",
        postgresql_where=text("handled_at IS NULL"),
    ),
)

backup_runs = Table(
    "backup_runs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("reason", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("snapshot_id", String(64), nullable=True),
    Column("data_added", BigInteger, nullable=True),
    Column("message", Text, nullable=True),
    CheckConstraint("reason IN ('daily', 'document', 'manual')", name="reason"),
    CheckConstraint(
        "status IN ('running', 'succeeded', 'failed', 'not_configured')", name="status"
    ),
)

# Saved column mappings of the import (field key -> column name in the file).
import_templates = Table(
    "import_templates",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("target", String(20), nullable=False),
    Column("name", String(60), nullable=False),
    Column("columns", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("target IN ('customers', 'articles', 'invoices')", name="target"),
    UniqueConstraint("target", "name", name="uq_import_templates_target_name"),
)

# What the onboarding checklist remembers; one row at most.
onboarding = Table(
    "onboarding",
    metadata,
    Column("singleton", Boolean, primary_key=True, server_default="true"),
    Column("numbering_checked_at", DateTime(timezone=True), nullable=True),
    Column("dismissed_at", DateTime(timezone=True), nullable=True),
    CheckConstraint("singleton", name="single_row"),
)

# How documents are laid out (domain/company/print_layout.py); one row at most.
print_layout = Table(
    "print_layout",
    metadata,
    Column("singleton", Boolean, primary_key=True, server_default="true"),
    Column("template", String(20), nullable=False),
    Column("logo_position", String(10), nullable=False),
    Column("logo_size", String(10), nullable=False),
    Column("font", String(10), nullable=False),
    Column("sender_line", Boolean, nullable=False),
    Column("contact", Boolean, nullable=False),
    Column("position_numbers", Boolean, nullable=False),
    Column("footer_accounts", String(20), nullable=False),
    Column("e_invoice", Boolean, nullable=False, server_default="true"),
    CheckConstraint("singleton", name="single_row"),
)

# The three dunning levels (domain/dunning/reminder.py); none saved: the defaults.
dunning_levels = Table(
    "dunning_levels",
    metadata,
    Column("level", SmallInteger, primary_key=True, autoincrement=False),
    Column("days_after_due", SmallInteger, nullable=False),
    Column("payment_days", SmallInteger, nullable=False),
    Column("fee", Numeric(10, 2), nullable=False),
    Column("text_de", Text, nullable=False),
    Column("text_en", Text, nullable=False),
    Column("text_fr", Text, nullable=False),
    Column("text_it", Text, nullable=False),
    CheckConstraint("level BETWEEN 1 AND 3", name="level"),
)

reminders = Table(
    "reminders",
    metadata,
    Column("id", Uuid(), primary_key=True),
    # The unique key below starts with the invoice: no index of its own.
    Column("invoice_id", Uuid(), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
    Column("level", SmallInteger, nullable=False),
    Column("issued_on", Date, nullable=False),
    Column("due_date", Date, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("open_amount", Numeric(14, 2), nullable=False),
    Column("fee", Numeric(10, 2), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("text", Text, nullable=False),
    CheckConstraint("level BETWEEN 1 AND 3", name="level"),
    # Each level once per invoice, also when two requests write it at the same time.
    UniqueConstraint("invoice_id", "level", name="uq_reminders_invoice_level"),
)

mail_server = Table(
    "mail_server",
    metadata,
    Column("singleton", Boolean, primary_key=True, server_default="true"),
    Column("host", String(253), nullable=False),
    Column("port", Integer, nullable=False),
    Column("security", String(10), nullable=False),
    Column("sender", String(254), nullable=False),
    Column("sender_name", String(120), nullable=False, server_default=""),
    Column("username", String(254), nullable=False, server_default=""),
    Column("password", String(500), nullable=False, server_default=""),
    Column("reply_to", String(254)),
    Column("copy_to_sender", Boolean, nullable=False),
    CheckConstraint("singleton", name="single_row"),
    CheckConstraint("security IN ('starttls', 'tls', 'none')", name="security"),
)

mail_templates = Table(
    "mail_templates",
    metadata,
    Column("kind", String(20), primary_key=True),
    Column("language", String(2), primary_key=True),
    Column("subject", String(200), nullable=False),
    Column("body", Text, nullable=False),
)

recurring_plans = Table(
    "recurring_plans",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("customer_id", Uuid(), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
    Column("interval", String(20), nullable=False),
    Column("start_date", Date, nullable=False),
    Column("next_date", Date, nullable=False),
    Column("end_date", Date),
    Column("action", String(10), nullable=False),
    Column("service_period", Boolean, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("template", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "interval IN ('monthly', 'quarterly', 'half_yearly', 'yearly')", name="interval"
    ),
    CheckConstraint("action IN ('draft', 'issue', 'send')", name="action"),
    CheckConstraint("end_date IS NULL OR end_date >= start_date", name="end"),
)

recurring_runs = Table(
    "recurring_runs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column(
        "plan_id",
        Uuid(),
        ForeignKey("recurring_plans.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("period_start", Date, nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("outcome", String(10), nullable=False),
    Column("document_id", Uuid(), ForeignKey("documents.id", ondelete="SET NULL")),
    Column("code", String(50), nullable=False, server_default=""),
    Column("message", String(500), nullable=False, server_default=""),
    UniqueConstraint("plan_id", "period_start", name="uq_recurring_runs_plan_period"),
    CheckConstraint("outcome IN ('draft', 'issued', 'sent', 'failed')", name="outcome"),
)
