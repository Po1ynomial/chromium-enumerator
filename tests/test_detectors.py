from pathlib import Path

from chrome_enumerator.detectors import classify_path, infer_family


def test_classifies_known_engine_frameworks():
    path = Path("/Applications/Foo.app/Contents/Frameworks/Electron Framework.framework")

    evidence = classify_path(path, is_executable=False)

    assert evidence is not None
    assert evidence.category == "engine"
    assert evidence.reason == "Electron Framework.framework"
    assert infer_family([evidence]) == "electron"


def test_classifies_runtime_resources():
    evidence = classify_path(
        Path("/Applications/Foo.app/Contents/Frameworks/Electron Framework.framework/Resources/icudtl.dat"),
        is_executable=False,
    )

    assert evidence is not None
    assert evidence.category == "resource"
    assert evidence.reason == "icudtl.dat"


def test_classifies_locale_pak_as_resource():
    evidence = classify_path(
        Path("/Applications/Foo.app/Contents/Frameworks/Electron Framework.framework/Resources/locales/en-US.pak"),
        is_executable=False,
    )

    assert evidence is not None
    assert evidence.category == "resource"
    assert evidence.reason == "locale pak"


def test_classifies_helper_apps_and_crashpad_handlers():
    helper = classify_path(Path("/Applications/Foo.app/Contents/Frameworks/Foo Helper.app"), is_executable=False)
    crashpad = classify_path(Path("/Applications/Foo.app/Contents/Frameworks/chrome_crashpad_handler"), is_executable=True)

    assert helper is not None
    assert helper.category == "helper"
    assert helper.reason == "Helper.app"
    assert crashpad is not None
    assert crashpad.category == "helper"
    assert crashpad.reason == "chrome_crashpad_handler"


def test_classifies_contents_macos_executable_entrypoint():
    evidence = classify_path(Path("/Applications/Foo.app/Contents/MacOS/Foo"), is_executable=True)

    assert evidence is not None
    assert evidence.category == "executable"
    assert evidence.reason == "Contents/MacOS executable"


def test_ignores_unrelated_files():
    assert classify_path(Path("/tmp/Foo.app/Contents/Resources/readme.txt"), is_executable=False) is None
