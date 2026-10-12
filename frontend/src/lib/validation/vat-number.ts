/**
 * VAT number checks mirroring rhinvoice.domain.tax.vat_number.
 * Only the Swiss UID has a check digit; DE/AT are checked for their format.
 */
export type VatProblem = "swiss-format" | "swiss-check-digit" | "german-format" | "austrian-format";

const SWISS = /^CHE[-\s]?(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})(?:\s*(MWST|TVA|IVA))?$/;
const WEIGHTS = [5, 4, 3, 2, 7, 6, 5, 4];

export function vatProblem(raw: string): VatProblem | null {
  const compact = raw.toUpperCase().trim().replace(/\s+/g, " ");
  if (compact === "") {
    return null;
  }
  if (compact.startsWith("CHE")) {
    const match = SWISS.exec(compact);
    if (match === null) {
      return "swiss-format";
    }
    const digits = match.slice(1, 4).join("");
    const total = WEIGHTS.reduce((sum, weight, index) => sum + weight * Number(digits[index]), 0);
    const check = (11 - (total % 11)) % 11;
    return check === Number(digits[8]) ? null : "swiss-check-digit";
  }
  const withoutSpaces = compact.replace(/ /g, "");
  if (withoutSpaces.startsWith("DE") && !/^DE\d{9}$/.test(withoutSpaces)) {
    return "german-format";
  }
  if (withoutSpaces.startsWith("AT") && !/^ATU\d{8}$/.test(withoutSpaces)) {
    return "austrian-format";
  }
  return null;
}
