from pathlib import Path

import pytest

from chromium_enumerator.platforms import (
    WindowsProfile,
    _install_root_from_uninstall,
    _parse_registry_exe_path,
)
from chromium_enumerator.scanner import ChromiumScanner


def make_file(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def make_large_payload(root: Path) -> Path:
    payload = root / "payload.bin"
    payload.parent.mkdir(parents=True, exist_ok=True)
    with payload.open("wb") as payload_file:
        payload_file.truncate(6 * 1024 * 1024)
    return payload


def make_cef_app(root: Path) -> Path:
    app = root / "cefapp"
    make_file(app / "cefapp.exe")
    make_file(app / "libcef.dll")
    make_file(app / "icudtl.dat")
    make_large_payload(app)
    return app


class RegistryStubProfile(WindowsProfile):
    def __init__(self, records: dict[Path, dict[str, str]]) -> None:
        self._records = records

    def registry_roots(self) -> dict[Path, dict[str, str]]:
        return self._records


def windows_scanner(profile=None, **kwargs) -> ChromiumScanner:
    return ChromiumScanner(
        profile=profile if profile is not None else WindowsProfile(), **kwargs
    )


def test_parse_registry_exe_path_handles_quotes_and_args(tmp_path):
    exe = tmp_path / "app" / "app.exe"
    make_file(exe)

    assert _parse_registry_exe_path(f'"{exe}" /flag') == exe
    assert _parse_registry_exe_path(str(exe)) == exe
    assert _parse_registry_exe_path(f'"{exe}",0') == exe


def test_parse_registry_exe_path_rejects_non_exe(tmp_path):
    assert _parse_registry_exe_path(str(tmp_path / "app" / "icon.ico")) is None
    assert _parse_registry_exe_path("") is None
    assert _parse_registry_exe_path(None) is None


def test_install_root_prefers_install_location(tmp_path):
    install = tmp_path / "app"
    install.mkdir()

    root = _install_root_from_uninstall({"InstallLocation": f'"{install}"'})

    assert root == install


def test_install_root_falls_back_to_display_icon_parent(tmp_path):
    exe = make_file(tmp_path / "app" / "app.exe")

    root = _install_root_from_uninstall({"DisplayIcon": f'"{exe}"'})

    assert root == exe.parent


def test_install_root_skips_uninstaller_icons(tmp_path):
    make_file(tmp_path / "app" / "unins000.exe")

    root = _install_root_from_uninstall(
        {"DisplayIcon": str(tmp_path / "app" / "unins000.exe")}
    )

    assert root is None


def test_registry_metadata_attached_to_matching_results(tmp_path):
    app = make_cef_app(tmp_path)
    profile = RegistryStubProfile(
        {
            app: {
                "DisplayName": "CEF Test App",
                "DisplayVersion": "9.9.9",
                "Publisher": "Example Corp",
                "source": "HKLM\\SOFTWARE\\...\\Uninstall",
            }
        }
    )

    [result] = windows_scanner(profile=profile).scan([tmp_path])

    assert result.registered_as == [
        {
            "DisplayName": "CEF Test App",
            "DisplayVersion": "9.9.9",
            "Publisher": "Example Corp",
            "source": "HKLM\\SOFTWARE\\...\\Uninstall",
        }
    ]


def test_registry_metadata_attached_via_ancestor_install(tmp_path):
    nested = tmp_path / "Suite" / "Tools" / "cefapp"
    make_file(nested / "cefapp.exe")
    make_file(nested / "libcef.dll")
    make_file(nested / "icudtl.dat")
    make_large_payload(nested)
    suite = tmp_path / "Suite"
    profile = RegistryStubProfile({suite: {"DisplayName": "Suite Installer"}})

    [result] = windows_scanner(profile=profile).scan([tmp_path])

    assert result.root == nested
    assert result.registered_as == [{"DisplayName": "Suite Installer"}]


def test_registry_only_filters_unregistered_candidates(tmp_path):
    registered = make_cef_app(tmp_path / "registered")
    make_cef_app(tmp_path / "unregistered")
    profile = RegistryStubProfile({registered: {"DisplayName": "Registered App"}})

    results = windows_scanner(profile=profile, registry_only=True).scan([tmp_path])

    assert [result.root for result in results] == [registered]


def test_registry_only_matches_ancestor_records(tmp_path):
    suite = tmp_path / "Suite"
    nested = suite / "cefapp"
    make_file(nested / "cefapp.exe")
    make_file(nested / "libcef.dll")
    make_file(nested / "icudtl.dat")
    make_large_payload(nested)
    make_cef_app(tmp_path / "other")
    profile = RegistryStubProfile({suite: {"DisplayName": "Suite"}})

    results = windows_scanner(profile=profile, registry_only=True).scan([tmp_path])

    assert [result.root for result in results] == [nested]


def test_registry_only_filters_everything_with_empty_registry(tmp_path):
    make_cef_app(tmp_path)
    profile = RegistryStubProfile({})

    results = windows_scanner(profile=profile, registry_only=True).scan([tmp_path])

    assert results == []


@pytest.mark.skipif(
    __import__("os").name == "nt", reason="asserts empty registry off-windows"
)
def test_windows_profile_registry_roots_empty_off_windows():
    assert WindowsProfile().registry_roots() == {}
