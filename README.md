# Bambu Cloud Status

A lightweight macOS menu bar app that shows the status of a linked Bambu Lab
printer using Bambu Cloud.

The app was built and tested for a Bambu Lab A1, but it should work with any
linked printer returned by the Bambu Cloud account.

It uses the Bambu Cloud API only. Local MQTT/LAN mode is not supported.

## Features

- Menu bar title shows quick status, such as `Idle`, `Printing 42%`, or `Error`
- Periodic cloud refresh every 60 seconds
- Optional manual refresh from the menu
- In-app configuration for region, Bambu Cloud credentials, and printer name
- Email verification code prompt when Bambu Cloud requires it
- Menu includes:
  - Printer name
  - Printer model
  - Current state
  - Progress
  - Online status
  - Last update timestamp
  - `Configure`
  - `Refresh now`
  - `Quit`

## Requirements

- macOS
- Python 3.10+
- A Bambu Cloud account
- At least one printer linked to that account

## Installation

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python app.py
```

The app appears in the macOS menu bar.

## Configuration

Open `Configure` from the app menu and enter:

- Region: `global` or `china`
- Bambu Cloud email
- Bambu Cloud password
- Optional printer name

If no printer name is provided, the app uses the first printer returned by the
Bambu Cloud account. If a printer name is provided, it must match the cloud
printer name exactly, ignoring letter case.

Login and verification are only attempted after the required settings are
entered. If Bambu Cloud requires an email verification code, the app requests it
in a macOS dialog.

## Security Notes

Settings are saved locally to:

```text
~/Library/Application Support/BambuCloudStatus/config.json
```

The local config file stores the region, email, and optional printer name. The
Bambu Cloud password is stored in macOS Keychain under the `BambuCloudStatus`
service.

Older config files that contain a plain-text password are migrated after a
successful refresh or configuration save, then rewritten without the password.

The password field in the configuration dialog is intentionally blank by default,
so existing credentials are not displayed when editing settings.

## Build a Standalone macOS App

Install py2app:

```bash
pip install py2app
```

Build the app bundle:

```bash
rm -rf build dist
python setup.py py2app
```

Open the generated app:

```bash
open dist/Bambu\ Cloud\ Status.app
```

## Auto-Start at Login

For a built app bundle, add `Bambu Cloud Status.app` to:

`System Settings` > `General` > `Login Items`

You can also create a `launchd` plist if you prefer to run the Python script
directly at login.

## Limitations

- Uses Bambu Cloud only; local MQTT/LAN mode is not supported
- Requires an internet connection
- Requires a working Bambu Cloud login
- Refreshes every 60 seconds
- Bambu Cloud endpoints are unofficial and may change
- Printer details are limited to the fields returned by the cloud account

## Troubleshooting

- Re-check the configured region, email, and password
- Confirm the printer is linked to the configured Bambu account
- Leave the optional printer name blank to use the first linked printer
- If a printer name is configured, confirm it matches the Bambu Cloud printer
  name
- If login requires verification, use the latest email verification code from
  Bambu
- If the app cannot read the Keychain password, open `Configure` and enter the
  account details again
- If the menu bar shows `Error`, choose `Refresh now` after checking the network
  connection
- If the app stops authenticating after working previously, Bambu may have
  changed its cloud API behavior

## Development Note

This project started as a first attempt at generating a small macOS utility with
an AI coding model.
