import os
from setuptools import setup

APP = ["app.py"]
DATA_FILES = [("assets", ["assets/app_icon.jpg"])]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/app_icon.jpg",
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
