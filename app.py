import json
import os
from datetime import datetime
from pathlib import Path

import requests
import rumps


class BambuCloudStatusApp(rumps.App):
    def __init__(self):
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.jpg")
        super().__init__("Starting…", icon=icon_path if os.path.exists(icon_path) else None, quit_button=None)

        self.config_path = (
            Path.home()
            / "Library"
            / "Application Support"
            / "BambuCloudStatus"
            / "config.json"
        )
        self.region = "global"
        self.email = ""
        self.password = ""
        self.printer_name = ""
        self.base = "https://api.bambulab.com"
        self.headers = {
            "User-Agent": "bambu_network_agent/01.09.05.01",
            "X-BBL-Client-Name": "OrcaSlicer",
            "X-BBL-Client-Type": "slicer",
            "X-BBL-Client-Version": "01.09.05.51",
            "X-BBL-Language": "en-US",
            "X-BBL-OS-Type": "mac",
            "X-BBL-OS-Version": "14.0",
            "X-BBL-Agent-Version": "01.09.05.01",
            "X-BBL-Executable-info": "{}",
            "X-BBL-Agent-OS-Type": "mac",
            "accept": "application/json",
            "Content-Type": "application/json",
        }

        self.access_token = ""
        self._last_error_message = ""

        self.status_item = rumps.MenuItem("Status: -")
        self.progress_item = rumps.MenuItem("Progress: -")
        self.online_item = rumps.MenuItem("Online: -")
        self.device_item = rumps.MenuItem("Printer: -")
        self.model_item = rumps.MenuItem("Model: -")
        self.updated_item = rumps.MenuItem("Last update: -")
        self.menu = [
            self.device_item,
            self.model_item,
            self.status_item,
            self.progress_item,
            self.online_item,
            self.updated_item,
            None,
            rumps.MenuItem("Configure", callback=self.configure),
            rumps.MenuItem("Refresh now", callback=self.refresh_now),
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        self._load_config()
        if self._is_config_complete():
            self._login()
            self._refresh_status()
        else:
            self._set_quick_title("setup")
            self.status_item.title = "Status: Configure account first"

        self.timer = rumps.Timer(self._refresh_status, 60)
        self.timer.start()

    def _is_config_complete(self):
        return bool(self.email and self.password and self.region in {"global", "china"})

    def _load_config(self):
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.region = str(data.get("region", "global")).strip().lower()
                self.email = str(data.get("email", "")).strip()
                self.password = str(data.get("password", "")).strip()
                self.printer_name = str(data.get("printer_name", "")).strip()
                self.base = "https://api.bambulab.cn" if self.region == "china" else "https://api.bambulab.com"
        except Exception:
            self.title = "Config error"

    def _save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(
                {
                    "region": self.region,
                    "email": self.email,
                    "password": self.password,
                    "printer_name": self.printer_name,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def configure(self, _=None):
        region_resp = rumps.Window(
            title="Configuration",
            message="Bambu Cloud region (global or china)",
            default_text=self.region if self.region in {"global", "china"} else "",
            ok="Next",
            cancel=True,
        ).run()
        if not region_resp.clicked:
            return
        region = (region_resp.text or "").strip().lower()
        if region not in {"global", "china"}:
            rumps.alert("Invalid region", "Please enter 'global' or 'china'.")
            return

        email_resp = rumps.Window(
            title="Configuration",
            message="Bambu Cloud email",
            default_text=self.email,
            ok="Next",
            cancel=True,
        ).run()
        if not email_resp.clicked:
            return
        email = (email_resp.text or "").strip()

        password_resp = rumps.Window(
            title="Configuration",
            message="Bambu Cloud password",
            default_text="",
            ok="Next",
            cancel=True,
            secure=True,
        ).run()
        if not password_resp.clicked:
            return
        password = (password_resp.text or "").strip()

        printer_resp = rumps.Window(
            title="Configuration",
            message="Optional printer name (leave empty for first printer)",
            default_text=self.printer_name,
            ok="Save",
            cancel=True,
        ).run()
        if not printer_resp.clicked:
            return

        if not email or not password:
            rumps.alert("Missing values", "Email and password are required.")
            return

        self.region = region
        self.email = email
        self.password = password
        self.printer_name = (printer_resp.text or "").strip()
        self.base = "https://api.bambulab.cn" if self.region == "china" else "https://api.bambulab.com"
        self._save_config()

        try:
            self._login()
            self._refresh_status()
            rumps.notification("Bambu Status", "Configuration saved", "Cloud login succeeded")
        except Exception as exc:
            self.title = "Login failed"
            self.status_item.title = "Status: Login failed"
            rumps.alert("Login failed", str(exc))

    def _login(self):
        login_url = f"{self.base}/v1/user-service/user/login"
        payload = {"account": self.email, "password": self.password, "apiError": ""}
        resp = requests.post(login_url, json=payload, headers=self.headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if (data.get("loginType") or "").strip() == "verifyCode":
            requests.post(
                f"{self.base}/v1/user-service/user/sendemail/code",
                json={"email": self.email, "type": "codeLogin"},
                headers=self.headers,
                timeout=20,
            ).raise_for_status()
            code = self._ask_code("Bambu verification", "Enter Bambu email verification code:")
            if not code:
                raise RuntimeError("Verification code is required")
            v = requests.post(
                login_url,
                json={"account": self.email, "code": code},
                headers=self.headers,
                timeout=20,
            )
            v.raise_for_status()
            data = v.json()
            if (data.get("loginType") or "").strip() == "verifyCode":
                raise RuntimeError("Invalid or expired verification code")

        token = data.get("accessToken") or ""
        if not token:
            raise RuntimeError("Cloud login failed: no access token returned")
        self.access_token = token

    @staticmethod
    def _ask_code(title: str, prompt: str) -> str:
        w = rumps.Window(message=prompt, title=title, default_text="", ok="Continue", cancel=True)
        resp = w.run()
        if resp.clicked and resp.text:
            return resp.text.strip()
        return ""

    def _pick_device(self, devices):
        if not devices:
            return None
        if self.printer_name:
            for d in devices:
                if (d.get("name") or "").strip().lower() == self.printer_name.lower():
                    return d
            raise RuntimeError(f"No cloud printer named '{self.printer_name}' found")
        return devices[0]

    def _set_quick_title(self, status: str, progress: int | None = None):
        normalized = (status or "unknown").strip().lower()
        if normalized in {"setup", "setup required"}:
            self.title = "Setup"
        elif normalized in {"error", "failed"}:
            self.title = "Error"
        elif normalized in {"running", "printing"}:
            if isinstance(progress, int):
                self.title = f"Printing {progress}%"
            else:
                self.title = "Printing"
        elif normalized:
            self.title = normalized.capitalize()
        else:
            self.title = "Unknown"

    def _refresh_status(self, _=None):
        if not self.access_token:
            return
        try:
            headers = dict(self.headers)
            headers["Authorization"] = f"Bearer {self.access_token}"
            resp = requests.get(f"{self.base}/v1/iot-service/api/user/bind", headers=headers, timeout=20)
            if resp.status_code == 401:
                # Token expired, attempt one re-login then retry.
                self._login()
                headers["Authorization"] = f"Bearer {self.access_token}"
                resp = requests.get(f"{self.base}/v1/iot-service/api/user/bind", headers=headers, timeout=20)
            resp.raise_for_status()
            devices = resp.json().get("devices", [])
            device = self._pick_device(devices)
            if not device:
                raise RuntimeError("No printers found in cloud account")

            name = device.get("name", "Unknown")
            model = device.get("dev_product_name") or device.get("dev_model_name") or "Unknown"
            status = device.get("print_status", "UNKNOWN")
            progress = device.get("mc_percent")
            if progress is None:
                progress = device.get("progress")
            try:
                progress = int(progress) if progress is not None else None
            except Exception:
                progress = None
            online = bool(device.get("online", False))
            now = datetime.now().strftime("%H:%M:%S")

            self._set_quick_title(status, progress)
            self.device_item.title = f"Printer: {name}"
            self.model_item.title = f"Model: {model}"
            self.status_item.title = f"Status: {status}"
            self.progress_item.title = (
                f"Progress: {progress}%" if isinstance(progress, int) else "Progress: -"
            )
            self.online_item.title = f"Online: {'Yes' if online else 'No'}"
            self.updated_item.title = f"Last update: {now}"
        except Exception as exc:
            self._set_quick_title("error")
            self.status_item.title = f"Status: Error"
            self.progress_item.title = "Progress: -"
            self.updated_item.title = f"Last update: {datetime.now().strftime('%H:%M:%S')}"
            msg = str(exc)
            if msg != self._last_error_message:
                rumps.notification("Bambu Status", "Cloud refresh failed", msg)
                self._last_error_message = msg

    def refresh_now(self, _):
        if not self.access_token:
            self.configure()
            return
        self._refresh_status()

    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    BambuCloudStatusApp().run()
