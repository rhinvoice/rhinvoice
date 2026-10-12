#!/bin/sh
# Writes the sample invoices of every tax case (backend/tests/einvoice_samples.py)
# as XML and, through Gotenberg, as PDF, and validates them (validate.sh).
set -eu

GOTENBERG_IMAGE="$(sed -n 's/^ *image: \(gotenberg\/gotenberg:.*\)$/\1/p' deploy/compose.yml)"
out="$(mktemp -d)"
container="rhinvoice-einvoice-gotenberg-$$"

cleanup() {
    docker rm --force "$container" >/dev/null 2>&1 || true
    rm -rf "$out"
}
trap cleanup EXIT

docker run --detach --name "$container" --publish 127.0.0.1::3000 "$GOTENBERG_IMAGE" >/dev/null
port="$(docker port "$container" 3000/tcp | head -n 1 | sed 's/.*://')"
attempts=0
until curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -gt 60 ]; then
        echo "Gotenberg did not start" >&2
        exit 1
    fi
    sleep 1
done

(cd backend && uv run python -m tests.einvoice_samples "$out" "http://127.0.0.1:$port")
ls "$out"

docker build --quiet --tag rhinvoice-einvoice-validators einvoice >/dev/null
docker run --rm --volume "$out:/in:ro" rhinvoice-einvoice-validators
