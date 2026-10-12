"""Write the OpenAPI schema to stdout (input for the generated frontend client)."""

import json
import sys

from rhinvoice.api.app import create_app
from rhinvoice.api.container import build_container
from rhinvoice.api.settings import Settings


def main() -> int:
    container = build_container(Settings())
    schema = create_app(container).openapi()
    container.engine.dispose()
    sys.stdout.write(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
