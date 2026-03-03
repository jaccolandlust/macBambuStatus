# Name: macBambuStatus

Description: 
A small local macOS menu bar app that shows your **Bambu Lab A1** printer status in the top taskbar.
 Bambu Menu Bar Status for macOS, a minimilistic app that tracks the current status
 of your Bambu Lab printer and displays that status in the status bar of your Mac.
 
 This is my first atempt at generating a program using an AI model. In this case gpt-5.3-codex.

It uses **Bambu Cloud API only** (no MQTT).

## Features

- Menu bar title shows quick status (e.g. `Idle`, `Printing 42%`, `Error`)
- Periodic cloud refresh (every 60s)
- Menu contains:
  - Current state
  - Progress
  - Bed/Nozzle temperatures
  - Last update timestamp
  - `Quit`

## Requirements

- macOS
- Python 3.10+
- Works with Bambu Cloud account and linked printer(s)

For **cloud mode**:

- Bambu account email + password

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run app:

```bash
python app.py
```

The app appears in the macOS menu bar.

4. Open **Configure** from the app menu and enter:
- Region (`global` or `china`)
- Bambu Cloud email
- Bambu Cloud password
- Optional printer name

Notes:
- Password field is intentionally blank by default (no prefilled credentials).
- Settings are saved locally to:
  - `~/Library/Application Support/BambuCloudStatus/config.json`
- Login/verification is only attempted after required settings are entered.
- Verification code is requested in an in-app macOS dialog.

## Build standalone macOS app (.app) with py2app

1. Install py2app:

```bash
pip install py2app
```

2. Build app bundle:

```bash
rm -rf build dist
python setup.py py2app
```

3. Open the generated app:

```bash
open dist/Bambu\ Cloud\ Status.app
```

## Auto-start at login (optional)

Create a small `launchd` plist or use a wrapper like `py2app` if you want a clickable app bundle.

## Troubleshooting

- Re-check region/email/password
- Confirm printer is linked to that Bambu account
