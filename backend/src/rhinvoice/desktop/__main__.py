"""``python -m rhinvoice.desktop``: how the installers start the program."""

from rhinvoice.desktop.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
