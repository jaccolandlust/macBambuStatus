import shutil
import subprocess
from pathlib import Path

from setuptools import setup


APP = ["app.py"]
ICON_SOURCE = Path("assets/app_icon.jpg")
GENERATED_ICON_DIR = Path("build/generated-icons")
ICONSET_SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]


def prepare_icons():
    if not ICON_SOURCE.exists():
        raise RuntimeError(f"Missing icon source: {ICON_SOURCE}")

    if not shutil.which("sips") or not shutil.which("iconutil"):
        raise RuntimeError("Building the macOS app icon requires sips and iconutil.")

    GENERATED_ICON_DIR.mkdir(parents=True, exist_ok=True)
    menu_icon = GENERATED_ICON_DIR / "app_icon.png"
    app_icon = GENERATED_ICON_DIR / "app_icon.icns"
    iconset = GENERATED_ICON_DIR / "app_icon.iconset"

    shutil.copyfile(ICON_SOURCE, menu_icon)

    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()

    for size, filename in ICONSET_SIZES:
        subprocess.run(
            [
                "sips",
                "-s",
                "format",
                "png",
                "-z",
                str(size),
                str(size),
                str(menu_icon),
                "--out",
                str(iconset / filename),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(app_icon)],
        check=True,
    )
    shutil.rmtree(iconset)
    return menu_icon, app_icon


MENU_ICON, APP_ICON = prepare_icons()
DATA_FILES = [("assets", [str(MENU_ICON)])]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": str(APP_ICON),
    "plist": {
        "CFBundleName": "Bambu Cloud Status",
        "CFBundleDisplayName": "Bambu Cloud Status",
        "CFBundleIdentifier": "com.local.bambucloudstatus",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,
    },
    "packages": ["rumps", "requests", "dotenv", "charset_normalizer"],
}

setup(
    app=APP,
    name="Bambu Cloud Status",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
