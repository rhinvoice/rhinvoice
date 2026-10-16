# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
"""French and Italian documents: dunning texts and ready-made text templates.

Languages are stored as two-letter strings, so documents, customers and mail
templates need no change. The dunning levels get a French and an Italian text
(the built-in ones for saved levels), and the ready-made templates of 0006 are
added in French and Italian.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-16 10:00:00.000000
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A copy of FRENCH_TEXTS and ITALIAN_TEXTS in domain/dunning/reminder.py at this revision.
DUNNING_TEXTS: dict[int, tuple[str, str]] = {
    1: (
        (
            "Sans doute cela vous a-t-il échappé : la facture suivante est encore ouverte. Nous "
            "vous prions de verser le montant d’ici au {faellig}. Si vous avez déjà effectué le "
            "paiement, veuillez ne pas tenir compte de ce courrier."
        ),
        (
            "Forse vi è sfuggito: la seguente fattura risulta ancora aperta. Vi preghiamo di "
            "versare l’importo entro il {faellig}. Se avete già effettuato il pagamento, vi "
            "preghiamo di non tenere conto di questa lettera."
        ),
    ),
    2: (
        (
            "Malgré notre rappel de paiement, la facture suivante n’est toujours pas payée. Nous "
            "vous prions de verser le montant ouvert d’ici au {faellig}."
        ),
        (
            "Nonostante il nostro promemoria di pagamento, la seguente fattura non è ancora stata "
            "pagata. Vi preghiamo di versare l’importo aperto entro il {faellig}."
        ),
    ),
    3: (
        (
            "La facture suivante est encore ouverte malgré notre rappel de paiement et notre "
            "premier rappel. Nous vous prions de verser le montant d’ici au {faellig}. À défaut, "
            "nous devrons faire valoir notre créance par voie juridique sans autre avis."
        ),
        (
            "La seguente fattura risulta ancora aperta nonostante il promemoria e il sollecito. Vi "
            "preghiamo di versare l’importo entro il {faellig}. In caso contrario dovremo far "
            "valere il credito per via legale senza ulteriore preavviso."
        ),
    ),
}

# Like the German and English ones of 0006. Placeholders: {nummer} {faellig}.
SEEDS: list[tuple[str, str, str, str, str, bool]] = [
    # kind, document type, language, name, text, default
    (
        "intro",
        "invoice",
        "fr",
        "Remerciement pour la commande",
        (
            "Nous vous remercions de votre commande et nous permettons de vous facturer les"
            " prestations suivantes :"
        ),
        True,
    ),
    ("payment", "invoice", "fr", "Échéance", "Payable jusqu’au {faellig}.", True),
    (
        "payment",
        "invoice",
        "fr",
        "Numéro de facture comme motif",
        (
            "Lors d’un virement par e-banking, veuillez indiquer le numéro de facture {nummer}"
            " dans le champ « Communication »."
        ),
        True,
    ),
    ("payment", "invoice", "fr", "Net sans escompte", "Payable net, sans escompte.", False),
    (
        "closing",
        "invoice",
        "fr",
        "Remerciement pour la collaboration",
        "Nous vous remercions de votre agréable collaboration.",
        True,
    ),
    (
        "intro",
        "quote",
        "fr",
        "Offre",
        (
            "Nous vous remercions de votre demande et avons le plaisir de vous soumettre"
            " l’offre suivante :"
        ),
        True,
    ),
    (
        "closing",
        "quote",
        "fr",
        "Validité",
        "Cette offre est valable jusqu’au {faellig}. Nous nous réjouissons de votre commande.",
        True,
    ),
    (
        "intro",
        "invoice",
        "it",
        "Ringraziamento per l’ordine",
        (
            "Vi ringraziamo per il vostro ordine e ci permettiamo di fatturarvi le seguenti"
            " prestazioni:"
        ),
        True,
    ),
    ("payment", "invoice", "it", "Scadenza", "Pagabile entro il {faellig}.", True),
    (
        "payment",
        "invoice",
        "it",
        "Numero di fattura come motivo",
        (
            "Per i pagamenti tramite e-banking vi preghiamo di indicare il numero di fattura"
            " {nummer} nel campo «Comunicazione»."
        ),
        True,
    ),
    ("payment", "invoice", "it", "Netto senza sconto", "Pagabile netto, senza sconto.", False),
    (
        "closing",
        "invoice",
        "it",
        "Ringraziamento per la collaborazione",
        "Vi ringraziamo per la piacevole collaborazione.",
        True,
    ),
    (
        "intro",
        "quote",
        "it",
        "Offerta",
        (
            "Vi ringraziamo per la vostra richiesta e abbiamo il piacere di sottoporvi la"
            " seguente offerta:"
        ),
        True,
    ),
    (
        "closing",
        "quote",
        "it",
        "Validità",
        (
            "La presente offerta è valida fino al {faellig}. Saremo lieti di ricevere il"
            " vostro ordine."
        ),
        True,
    ),
]


def upgrade() -> None:
    for column in ("text_fr", "text_it"):
        op.add_column(
            "dunning_levels", sa.Column(column, sa.Text(), server_default="", nullable=False)
        )
    for level, (french, italian) in DUNNING_TEXTS.items():
        op.execute(
            sa.text(
                "UPDATE dunning_levels SET text_fr = :french, text_it = :italian"
                " WHERE level = :level"
            ).bindparams(french=french, italian=italian, level=level)
        )
    for column in ("text_fr", "text_it"):
        op.alter_column("dunning_levels", column, server_default=None)

    templates = sa.table(
        "text_templates",
        sa.column("id", sa.Uuid()),
        sa.column("kind", sa.String()),
        sa.column("document_type", sa.String()),
        sa.column("language", sa.String()),
        sa.column("name", sa.String()),
        sa.column("text", sa.Text()),
        sa.column("is_default", sa.Boolean()),
        sa.column("position", sa.Integer()),
    )
    positions: dict[tuple[str, str, str], int] = {}
    rows: list[dict[str, object]] = []
    for kind, document_type, language, name, text, is_default in SEEDS:
        key = (kind, document_type, language)
        positions[key] = positions.get(key, -1) + 1
        rows.append(
            {
                "id": uuid.uuid4(),
                "kind": kind,
                "document_type": document_type,
                "language": language,
                "name": name,
                "text": text,
                "is_default": is_default,
                "position": positions[key],
            },
        )
    op.bulk_insert(templates, rows)


def downgrade() -> None:
    """Remove what only French and Italian use; drafts and defaults fall back to German.

    Issued documents in French or Italian cannot change (they are immutable) and
    stay as they are: an older Rhinvoice cannot read them.
    """
    for table in ("text_templates", "legal_notices", "mail_templates"):
        op.execute(sa.text(f"DELETE FROM {table} WHERE language IN ('fr', 'it')"))  # noqa: S608 - constant table names
    op.execute("UPDATE company SET default_language = 'de' WHERE default_language IN ('fr', 'it')")
    op.execute(
        "UPDATE customers SET default_language = NULL WHERE default_language IN ('fr', 'it')"
    )
    op.execute(
        "UPDATE documents SET language = 'de' WHERE status = 'draft' AND language IN ('fr', 'it')"
    )
    op.execute(
        "UPDATE recurring_plans SET template = jsonb_set(template, '{language}', '\"de\"')"
        " WHERE template->>'language' IN ('fr', 'it')"
    )
    op.drop_column("dunning_levels", "text_it")
    op.drop_column("dunning_levels", "text_fr")
