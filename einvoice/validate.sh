#!/bin/sh
# Validates every e-invoice in /in: XML files with the KoSIT validator (EN 16931,
# XRechnung), PDF files with Mustang (ZUGFeRD / Factur-X, PDF/A-3).
# Fails on any rejection, error or warning.
set -eu

cd /opt/einvoice
status=0

echo "--- KoSIT validator: EN 16931 and XRechnung"
if ! java -jar kosit.jar -s xrechnung/scenarios.xml -r xrechnung -o /tmp /in/*.xml; then
    status=1
fi
# Warnings do not fail the KoSIT run; they fail this check.
if grep -l 'flag="warning"' /tmp/*-report.xml; then
    echo "warnings in the reports above" >&2
    status=1
fi

echo "--- Mustang: ZUGFeRD / Factur-X PDFs"
for pdf in /in/*.pdf; do
    # Mustang exits non-zero for invalid files; the report says why.
    if report="$(cd /tmp && java -jar /opt/einvoice/mustang.jar --action validate --source "$pdf" --no-notices 2>&1)"; then
        valid=yes
    else
        valid=no
    fi
    if [ "$valid" = no ] || printf '%s\n' "$report" | grep -q -E '<(error|warning)|summary status="invalid"'; then
        echo "FAIL $pdf" >&2
        printf '%s\n' "$report" >&2
        status=1
    else
        echo "PASS $pdf"
    fi
done
exit "$status"
