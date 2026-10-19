"""desktop/release_manifest.py: writing, signing and checking release.json (ADR 0022, 0033)."""

import base64
import importlib.util
import json
import re
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rhinvoice.infrastructure.updates.feed import PUBLIC_KEY, read_release

# The nearest one upwards: mutmut runs the tests from a copy inside backend/mutants.
SCRIPT = next(
    folder / "desktop" / "release_manifest.py"
    for folder in Path(__file__).parents
    if (folder / "desktop" / "release_manifest.py").exists()
)
TAG = "v0.9.0-rc.2"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load()
KEY = Ed25519PrivateKey.generate()
PEM = KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
PUBLIC = base64.b64encode(
    KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()


@pytest.fixture(autouse=True)
def test_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sign with a key of the test; the program's private key is never in the repository."""
    monkeypatch.setattr(tool, "PUBLIC_KEY", PUBLIC)


def package(folder: Path, version: str = "0.9.0", runtime: int = 2, candidate: object = 2) -> Path:
    """Write an app package built as candidate 2 (TAG), or as none with ``candidate=None``."""
    path = folder / f"rhinvoice-app-{version}-windows-x64.zip"
    manifest: dict[str, object] = {"version": version, "runtime": runtime}
    if candidate is not None:
        manifest["candidate"] = candidate
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    return path


def release_files(folder: Path) -> Path:
    folder.mkdir()
    package(folder)
    (folder / "Rhinvoice-Setup-Windows.exe").write_bytes(b"setup for windows")
    (folder / "Rhinvoice-Beta-macOS.dmg").write_bytes(b"beta for macos")
    return folder


def candidate(tmp_path: Path) -> tuple[Path, Path]:
    """Build a candidate with its signed release.json; return it and the files promoted."""
    built = release_files(tmp_path / "candidate")
    tool.write_signed("0.9.0", built, TAG, PEM)
    taken = tmp_path / "release"
    taken.mkdir()
    for name in ("rhinvoice-app-0.9.0-windows-x64.zip", "Rhinvoice-Setup-Windows.exe"):
        (taken / name).write_bytes((built / name).read_bytes())
    return built, taken


def test_carries_the_programs_public_key() -> None:
    assert load().PUBLIC_KEY == PUBLIC_KEY


def test_writes_a_release_json_the_program_reads(tmp_path: Path) -> None:
    folder = release_files(tmp_path / "release")

    tool.write_signed("0.9.0", folder, TAG, PEM)

    content = (folder / "release.json").read_bytes()
    tool.check_signature(content, (folder / "release.json.sig").read_bytes())
    release = read_release(json.loads(content))
    assert release.version == "0.9.0"
    assert release.runtime == 2
    assert release.notes_url == f"https://github.com/rhinvoice/rhinvoice/releases/tag/{TAG}"
    assert list(release.packages) == ["windows-x64"]
    assert release.packages["windows-x64"].url.endswith(
        f"/download/{TAG}/rhinvoice-app-0.9.0-windows-x64.zip"
    )
    assert set(release.setup_files) == {"windows-x64", "macos-arm64-beta"}
    assert release.setup_files["windows-x64"].size == len(b"setup for windows")
    assert release.setups["windows-x64"] == release.setup_files["windows-x64"].url
    assert release.candidate == 2


def test_the_release_names_the_candidate_it_was_promoted_from(tmp_path: Path) -> None:
    """ADR 0035: Rhinvoice Beta on that candidate is not offered the same files again."""
    _, taken = candidate(tmp_path)

    release = tool.write_signed("0.9.0", taken, "v0.9.0", PEM)

    assert release["candidate"] == 2


def test_packages_without_a_candidate_name_none(tmp_path: Path) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    package(folder, candidate=None)

    assert "candidate" not in tool.write_signed("0.9.0", folder, "v0.9.0", PEM)


@pytest.mark.parametrize(
    ("built_as", "message"),
    [
        (3, "was built as candidate 3, not as v0.9.0-rc.2"),
        (None, "was built as candidate None, not as v0.9.0-rc.2"),
        (0, "names no candidate's number: 0"),
        ("2", "names no candidate's number: '2'"),
        (True, "names no candidate's number: True"),
    ],
)
def test_refuses_a_package_not_built_as_this_candidate(
    tmp_path: Path, built_as: object, message: str
) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    package(folder, candidate=built_as)

    with pytest.raises(SystemExit, match=re.escape(message)):
        tool.write_signed("0.9.0", folder, TAG, PEM)


def test_refuses_packages_built_as_different_candidates(tmp_path: Path) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    package(folder, candidate=3).rename(folder / "rhinvoice-app-0.9.0-macos-arm64.zip")
    package(folder, candidate=None)

    with pytest.raises(SystemExit, match="built as different candidates"):
        tool.write_signed("0.9.0", folder, "v0.9.0", PEM)


def test_a_server_release_has_runtime_one(tmp_path: Path) -> None:
    folder = tmp_path / "release"
    folder.mkdir()

    release = tool.write_signed("0.9.0", folder, "v0.9.0", PEM)

    assert release["runtime"] == 1
    assert release["packages"] == {}


def test_refuses_a_package_of_another_version(tmp_path: Path) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    package(folder, version="0.8.0").rename(folder / "rhinvoice-app-0.9.0-windows-x64.zip")

    with pytest.raises(SystemExit, match=re.escape("holds version 0.8.0, not 0.9.0")):
        tool.write_signed("0.9.0", folder, TAG, PEM)


def test_refuses_packages_for_different_runtimes(tmp_path: Path) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    package(folder, runtime=2)
    package(folder, runtime=3).rename(folder / "rhinvoice-app-0.9.0-macos-arm64.zip")
    package(folder, runtime=2)

    with pytest.raises(SystemExit, match=r"different runtimes: \[2, 3\]"):
        tool.write_signed("0.9.0", folder, TAG, PEM)


def test_refuses_a_key_that_is_not_ed25519(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric import ec  # noqa: PLC0415

    other = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    with pytest.raises(SystemExit, match="not an Ed25519 key"):
        tool.write_signed("0.9.0", release_files(tmp_path / "r"), TAG, other.decode())


def test_refuses_a_key_the_program_does_not_trust(tmp_path: Path) -> None:
    other = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    folder = release_files(tmp_path / "release")

    with pytest.raises(SystemExit, match="does not match the program's public key"):
        tool.write_signed("0.9.0", folder, TAG, other.decode())
    assert not (folder / "release.json").exists()


def test_refuses_a_signature_that_is_no_base64() -> None:
    with pytest.raises(SystemExit, match="does not match"):
        tool.check_signature(b"{}", b"not base64!")


def test_accepts_the_candidates_files(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)

    names = tool.verify_candidate("0.9.0", taken, built, TAG)

    assert names == ["Rhinvoice-Setup-Windows.exe", "rhinvoice-app-0.9.0-windows-x64.zip"]


def test_refuses_a_changed_file(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)
    # Same size, other content: only the SHA-256 tells.
    (taken / "Rhinvoice-Setup-Windows.exe").write_bytes(b"setup for WINDOWS")

    with pytest.raises(SystemExit, match=re.escape("Rhinvoice-Setup-Windows.exe differs")):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def test_refuses_a_file_of_another_size(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)
    (taken / "Rhinvoice-Setup-Windows.exe").write_bytes(b"setup")

    with pytest.raises(SystemExit, match="differs"):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def test_refuses_a_file_the_candidate_does_not_list(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)
    (taken / "Rhinvoice-macOS.dmg").write_bytes(b"from somewhere")

    with pytest.raises(SystemExit, match=re.escape("Rhinvoice-macOS.dmg is not in the candidate")):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def test_refuses_when_a_file_of_the_candidate_is_missing(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)
    # E.g. a setup the download pattern did not match: it would drop out of the release.
    (taken / "Rhinvoice-Setup-Windows.exe").unlink()

    with pytest.raises(SystemExit, match=r"candidate's Rhinvoice-Setup-Windows\.exe is missing"):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def test_does_not_expect_the_beta_setups(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)

    assert "Rhinvoice-Beta-macOS.dmg" in (built / "release.json").read_text()
    assert "Rhinvoice-Beta-macOS.dmg" not in tool.verify_candidate("0.9.0", taken, built, TAG)


def test_refuses_a_changed_release_json(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)
    manifest = built / "release.json"
    manifest.write_bytes(manifest.read_bytes().replace(b'"runtime": 2', b'"runtime": 3'))

    with pytest.raises(SystemExit, match="does not match the program's public key"):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def test_refuses_the_candidate_of_another_version(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)

    with pytest.raises(SystemExit, match=re.escape("is for '0.9.0', not 0.9.1")):
        tool.verify_candidate("0.9.1", taken, built, TAG)


def test_refuses_files_of_another_candidate(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)

    with pytest.raises(SystemExit, match=re.escape("is no file of v0.9.0-rc.3")):
        tool.verify_candidate("0.9.0", taken, built, "v0.9.0-rc.3")


def test_refuses_an_empty_folder(tmp_path: Path) -> None:
    built, taken = candidate(tmp_path)
    for path in taken.iterdir():
        path.unlink()

    with pytest.raises(SystemExit, match="holds no files"):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def signed_release(folder: Path, values: object) -> Path:
    folder.mkdir()
    content = json.dumps(values).encode()
    (folder / "release.json").write_bytes(content)
    (folder / "release.json.sig").write_bytes(base64.b64encode(KEY.sign(content)))
    return folder


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([], "is not an object"),
        ({"version": "0.9.0", "packages": []}, "'packages' is not an object"),
        ({"version": "0.9.0", "setup_files": {"windows-x64": "x"}}, "is not an object"),
        (
            {"version": "0.9.0", "packages": {"windows-x64": {"url": 1, "sha256": "ab"}}},
            "is no file of",
        ),
        (
            {
                "version": "0.9.0",
                "packages": {
                    "windows-x64": {
                        "url": f"https://github.com/rhinvoice/rhinvoice/releases/download/{TAG}/a",
                        "size": 1,
                    }
                },
            },
            "with a SHA-256",
        ),
        (
            {
                "version": "0.9.0",
                "packages": {
                    "windows-x64": {
                        "url": f"https://github.com/rhinvoice/rhinvoice/releases/download/{TAG}/a",
                        "sha256": "ab",
                        "size": True,
                    }
                },
            },
            "has no size",
        ),
    ],
)
def test_refuses_a_signed_release_json_of_another_format(
    tmp_path: Path, values: object, message: str
) -> None:
    built = signed_release(tmp_path / "candidate", values)
    taken = tmp_path / "release"
    taken.mkdir()
    (taken / "a").write_bytes(b"a")

    with pytest.raises(SystemExit, match=message):
        tool.verify_candidate("0.9.0", taken, built, TAG)


def test_main_signs_with_the_key_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = release_files(tmp_path / "release")
    monkeypatch.setenv("RELEASE_SIGNING_KEY", PEM)

    tool.main(["0.9.0", str(folder), "--tag", TAG])

    assert (folder / "release.json.sig").exists()
    assert "release.json for 0.9.0 signed; app packages: windows-x64" in capsys.readouterr().out


def test_main_names_a_server_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    monkeypatch.setenv("RELEASE_SIGNING_KEY", PEM)

    tool.main(["0.9.0", str(folder)])

    assert "none (server release)" in capsys.readouterr().out
    assert b"/releases/tag/v0.9.0" in (folder / "release.json").read_bytes()


def test_main_needs_the_key_to_sign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RELEASE_SIGNING_KEY", raising=False)

    with pytest.raises(SystemExit, match="set RELEASE_SIGNING_KEY"):
        tool.main(["0.9.0", str(tmp_path)])


def test_main_verifies_without_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    built, taken = candidate(tmp_path)
    monkeypatch.delenv("RELEASE_SIGNING_KEY", raising=False)

    tool.main(["0.9.0", str(taken), "--verify", str(built), "--tag", TAG])

    assert f"2 files are the candidate's {TAG}" in capsys.readouterr().out
    assert not (taken / "release.json").exists()
