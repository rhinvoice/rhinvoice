# Rhinvoice without Docker (Windows and Mac)

A setup for Windows (`Rhinvoice-Setup-x.y.z.exe`) and a disk image for Macs with Apple silicon
(`Rhinvoice-x.y.z.dmg`) on the [GitHub releases](https://github.com/rhinvoice/rhinvoice/releases).
Beta. The Mac apps are signed with the Developer ID and notarized by Apple, the Windows setups
signed with Azure Artifact Signing (ADR 0036). While the Windows certificate is new, SmartScreen
may still ask once ("More info" → "Run anyway").

| | Program | Data |
|---|---|---|
| Windows | `%LOCALAPPDATA%\Programs\Rhinvoice` | `%LOCALAPPDATA%\Rhinvoice` |
| Mac | `/Applications/Rhinvoice.app` | `~/Library/Application Support/Rhinvoice` |

- Updates come inside the program (ADR 0022); uninstalling keeps the data folder.
- Backups: Settings → Backup, a folder and a recovery key (ADR 0023). Restore with
  `--restore latest` (Mac: `Rhinvoice.app/Contents/MacOS/Rhinvoice`, Windows:
  `python\python.exe -P -m rhinvoice_boot` in the program folder).
- Building: `desktop/build.py`; architecture: ADR 0021, 0022, 0023.

User guide: [rhinvoice.com/docs/getting-started/install-desktop](https://rhinvoice.com/docs/getting-started/install-desktop/).
