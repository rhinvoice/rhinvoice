from enum import StrEnum


class Language(StrEnum):
    """The languages of documents, mails and legal notices.

    French and Italian are written as in Switzerland (fr-CH, it-CH), see ADR 0026.
    """

    DE = "de"
    EN = "en"
    FR = "fr"
    IT = "it"
