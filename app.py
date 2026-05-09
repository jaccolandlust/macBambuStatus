import ctypes
import json
import os
import threading
from datetime import datetime
from pathlib import Path

import requests
import rumps
from PyObjCTools import AppHelper


class AuthExpired(RuntimeError):
    pass


class KeychainError(RuntimeError):
    pass


class BambuCloudStatusApp(rumps.App):
    KEYCHAIN_SERVICE = "BambuCloudStatus"
    ERR_SEC_SUCCESS = 0
    ERR_SEC_DUPLICATE_ITEM = -25299
    ERR_SEC_ITEM_NOT_FOUND = -25300

    _security = None
    _corefoundation = None

    def __init__(self):
        icon_path = self._menu_icon_path()
        super().__init__("Starting", icon=icon_path if os.path.exists(icon_path) else None, quit_button=None)

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
        self._config_error_message = ""
        self._config_has_plaintext_password = False
        self._has_saved_account = False
        self._refresh_in_progress = False
        self._state_lock = threading.Lock()
        self._config_generation = 0

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
        if self._config_error_message:
            self._set_config_error(self._config_error_message)
        elif self._can_attempt_refresh():
            self.status_item.title = "Status: Starting"
            self.startup_timer = rumps.Timer(self._startup_refresh, 1)
            self.startup_timer.start()
        else:
            self._set_setup_required()

        self.timer = rumps.Timer(self._refresh_async, 60)
        self.timer.start()

    @staticmethod
    def _menu_icon_path():
        app_dir = os.path.dirname(__file__)
        png_path = os.path.join(app_dir, "assets", "app_icon.png")
        if os.path.exists(png_path):
            return png_path
        return os.path.join(app_dir, "assets", "app_icon.jpg")

    @staticmethod
    def _base_for_region(region):
        return "https://api.bambulab.cn" if region == "china" else "https://api.bambulab.com"

    def _can_attempt_refresh(self):
        return bool(
            self.email
            and self.region in {"global", "china"}
            and (self.password or self._has_saved_account)
        )

    def _load_config(self):
        try:
            if not self.config_path.exists():
                return

            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.region = str(data.get("region", "global")).strip().lower()
            self.email = str(data.get("email", "")).strip()
            self.printer_name = str(data.get("printer_name", "")).strip()
            self.base = self._base_for_region(self.region)
            self._has_saved_account = bool(self.email and self.region in {"global", "china"})

            legacy_password = str(data.get("password", "")).strip()
            self._config_has_plaintext_password = bool(legacy_password)
            self.password = legacy_password
        except Exception as exc:
            self._config_error_message = f"Could not read config file: {exc}"

    def _write_config_values(self, region, email, printer_name):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.config_path.parent, 0o700)
        except OSError:
            pass

        temp_path = self.config_path.with_name(f"{self.config_path.name}.tmp")
        temp_path.write_text(
            json.dumps(
                {
                    "region": region,
                    "email": email,
                    "printer_name": printer_name,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        os.chmod(temp_path, 0o600)
        temp_path.replace(self.config_path)
        os.chmod(self.config_path, 0o600)

    @classmethod
    def _load_keychain_frameworks(cls):
        if cls._security is not None and cls._corefoundation is not None:
            return cls._security, cls._corefoundation

        security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        corefoundation = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )

        security.SecKeychainAddGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        security.SecKeychainAddGenericPassword.restype = ctypes.c_int32

        security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        security.SecKeychainFindGenericPassword.restype = ctypes.c_int32

        security.SecKeychainItemModifyAttributesAndData.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32

        security.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        security.SecKeychainItemFreeContent.restype = ctypes.c_int32

        corefoundation.CFRelease.argtypes = [ctypes.c_void_p]
        corefoundation.CFRelease.restype = None

        cls._security = security
        cls._corefoundation = corefoundation
        return security, corefoundation

    @classmethod
    def _keychain_account(cls, region, email):
        return f"{region}:{email}"

    @classmethod
    def _raise_keychain_error(cls, action, status):
        raise KeychainError(f"{action} failed with OSStatus {status}")

    @classmethod
    def _find_keychain_password(cls, region, email):
        security, _ = cls._load_keychain_frameworks()
        service = cls.KEYCHAIN_SERVICE.encode("utf-8")
        account = cls._keychain_account(region, email).encode("utf-8")
        password_length = ctypes.c_uint32()
        password_data = ctypes.c_void_p()

        status = security.SecKeychainFindGenericPassword(
            None,
            len(service),
            service,
            len(account),
            account,
            ctypes.byref(password_length),
            ctypes.byref(password_data),
            None,
        )
        if status == cls.ERR_SEC_ITEM_NOT_FOUND:
            return ""
        if status != cls.ERR_SEC_SUCCESS:
            cls._raise_keychain_error("Reading Keychain password", status)

        try:
            raw = ctypes.string_at(password_data, password_length.value)
            return raw.decode("utf-8")
        finally:
            security.SecKeychainItemFreeContent(None, password_data)

    @classmethod
    def _save_keychain_password(cls, region, email, password):
        security, corefoundation = cls._load_keychain_frameworks()
        service = cls.KEYCHAIN_SERVICE.encode("utf-8")
        account = cls._keychain_account(region, email).encode("utf-8")
        password_bytes = password.encode("utf-8")
        password_buffer = ctypes.create_string_buffer(password_bytes)
        item_ref = ctypes.c_void_p()

        status = security.SecKeychainAddGenericPassword(
            None,
            len(service),
            service,
            len(account),
            account,
            len(password_bytes),
            ctypes.cast(password_buffer, ctypes.c_void_p),
            ctypes.byref(item_ref),
        )
        if item_ref.value:
            corefoundation.CFRelease(item_ref)

        if status == cls.ERR_SEC_SUCCESS:
            return
        if status != cls.ERR_SEC_DUPLICATE_ITEM:
            cls._raise_keychain_error("Saving Keychain password", status)

        item_ref = ctypes.c_void_p()
        status = security.SecKeychainFindGenericPassword(
            None,
            len(service),
            service,
            len(account),
            account,
            None,
            None,
            ctypes.byref(item_ref),
        )
        if status != cls.ERR_SEC_SUCCESS:
            cls._raise_keychain_error("Finding existing Keychain password", status)

        try:
            status = security.SecKeychainItemModifyAttributesAndData(
                item_ref,
                None,
                len(password_bytes),
                ctypes.cast(password_buffer, ctypes.c_void_p),
            )
        finally:
            if item_ref.value:
                corefoundation.CFRelease(item_ref)

        if status != cls.ERR_SEC_SUCCESS:
            cls._raise_keychain_error("Updating Keychain password", status)

    def _save_credentials(self, region, email, password, printer_name):
        self._save_keychain_password(region, email, password)
        self._write_config_values(region, email, printer_name)

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

        printer_name = (printer_resp.text or "").strip()
        self._set_quick_title("checking")
        self.status_item.title = "Status: Checking configuration"
        self.progress_item.title = "Progress: -"
        self._configure_async(region, email, password, printer_name)

    def _configure_async(self, region, email, password, printer_name):
        with self._state_lock:
            self._config_generation += 1
            generation = self._config_generation

        def worker():
            try:
                token = self._login_with_credentials(region, email, password)
                status = self._fetch_status(self._base_for_region(region), token, printer_name)
                self._save_credentials(region, email, password, printer_name)
            except Exception as exc:
                AppHelper.callAfter(self._finish_configure_error, str(exc), generation)
            else:
                AppHelper.callAfter(
                    self._finish_configure_success,
                    region,
                    email,
                    password,
                    printer_name,
                    token,
                    status,
                    generation,
                )

        threading.Thread(target=worker, name="BambuConfigure", daemon=True).start()

    def _finish_configure_success(
        self,
        region,
        email,
        password,
        printer_name,
        token,
        status,
        generation,
    ):
        with self._state_lock:
            if generation != self._config_generation:
                return
            self.region = region
            self.email = email
            self.password = password
            self.printer_name = printer_name
            self.base = self._base_for_region(region)
            self.access_token = token
            self._config_error_message = ""
            self._config_has_plaintext_password = False
            self._has_saved_account = True
            self._last_error_message = ""

        self._apply_status(status)
        rumps.notification("Bambu Status", "Configuration saved", "Cloud login succeeded")

    def _finish_configure_error(self, message, generation):
        with self._state_lock:
            if generation != self._config_generation:
                return

        self.title = "Login failed"
        self.status_item.title = "Status: Login failed"
        self.progress_item.title = "Progress: -"
        rumps.alert("Login failed", message)

    def _login_with_credentials(self, region, email, password):
        base = self._base_for_region(region)
        login_url = f"{base}/v1/user-service/user/login"
        payload = {"account": email, "password": password, "apiError": ""}
        resp = requests.post(login_url, json=payload, headers=self.headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if (data.get("loginType") or "").strip() == "verifyCode":
            requests.post(
                f"{base}/v1/user-service/user/sendemail/code",
                json={"email": email, "type": "codeLogin"},
                headers=self.headers,
                timeout=20,
            ).raise_for_status()
            code = self._ask_code("Bambu verification", "Enter Bambu email verification code:")
            if not code:
                raise RuntimeError("Verification code is required")
            v = requests.post(
                login_url,
                json={"account": email, "code": code},
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
        return token

    @staticmethod
    def _show_code_window(title, prompt):
        w = rumps.Window(message=prompt, title=title, default_text="", ok="Continue", cancel=True)
        resp = w.run()
        if resp.clicked and resp.text:
            return resp.text.strip()
        return ""

    def _ask_code(self, title, prompt):
        if threading.current_thread() is threading.main_thread():
            return self._show_code_window(title, prompt)

        done = threading.Event()
        result = {"code": "", "error": None}

        def prompt_on_main_thread():
            try:
                result["code"] = self._show_code_window(title, prompt)
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()

        AppHelper.callAfter(prompt_on_main_thread)
        done.wait()
        if result["error"] is not None:
            raise result["error"]
        return result["code"]

    @staticmethod
    def _pick_device(devices, printer_name):
        if not devices:
            return None
        if printer_name:
            for device in devices:
                if (device.get("name") or "").strip().lower() == printer_name.lower():
                    return device
            raise RuntimeError(f"No cloud printer named '{printer_name}' found")
        return devices[0]

    @staticmethod
    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "online"}
        return bool(value)

    def _set_quick_title(self, status, progress=None):
        normalized = (status or "unknown").strip().lower()
        if normalized in {"setup", "setup required"}:
            self.title = "Setup"
        elif normalized in {"checking", "starting", "refreshing"}:
            self.title = normalized.capitalize()
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

    def _set_setup_required(self):
        self._set_quick_title("setup")
        self.device_item.title = "Printer: -"
        self.model_item.title = "Model: -"
        self.status_item.title = "Status: Configure account first"
        self.progress_item.title = "Progress: -"
        self.online_item.title = "Online: -"
        self.updated_item.title = "Last update: -"

    def _set_config_error(self, message):
        self._set_quick_title("error")
        self.device_item.title = "Printer: Config error"
        self.model_item.title = "Model: -"
        self.status_item.title = f"Status: {message}"
        self.progress_item.title = "Progress: -"
        self.online_item.title = "Online: -"
        self.updated_item.title = "Last update: -"

    def _startup_refresh(self, timer):
        timer.stop()
        self._refresh_async()

    def _refresh_async(self, _=None):
        if not self._can_attempt_refresh():
            return

        with self._state_lock:
            if self._refresh_in_progress:
                return
            self._refresh_in_progress = True
            snapshot = {
                "region": self.region,
                "email": self.email,
                "password": self.password,
                "printer_name": self.printer_name,
                "access_token": self.access_token,
                "generation": self._config_generation,
                "migrate_plaintext": self._config_has_plaintext_password,
            }

        def worker():
            try:
                token, status, migrated_plaintext, password = self._refresh_status_snapshot(snapshot)
            except Exception as exc:
                AppHelper.callAfter(
                    self._finish_refresh_error,
                    str(exc),
                    snapshot["generation"],
                )
            else:
                AppHelper.callAfter(
                    self._finish_refresh_success,
                    token,
                    status,
                    snapshot["generation"],
                    migrated_plaintext,
                    password,
                )

        threading.Thread(target=worker, name="BambuRefresh", daemon=True).start()

    def _refresh_status_snapshot(self, snapshot):
        region = snapshot["region"]
        email = snapshot["email"]
        password = snapshot["password"]
        printer_name = snapshot["printer_name"]
        token = snapshot["access_token"]
        base = self._base_for_region(region)

        if not password:
            password = self._find_keychain_password(region, email)
            if not password:
                raise RuntimeError("No Keychain password saved; open Configure and enter credentials again")

        if not token:
            token = self._login_with_credentials(region, email, password)

        try:
            status = self._fetch_status(base, token, printer_name)
        except AuthExpired:
            token = self._login_with_credentials(region, email, password)
            status = self._fetch_status(base, token, printer_name)

        migrated_plaintext = False
        if snapshot["migrate_plaintext"]:
            self._save_credentials(region, email, password, printer_name)
            migrated_plaintext = True

        return token, status, migrated_plaintext, password

    def _fetch_status(self, base, token, printer_name):
        headers = dict(self.headers)
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(f"{base}/v1/iot-service/api/user/bind", headers=headers, timeout=20)
        if resp.status_code == 401:
            raise AuthExpired("Cloud token expired")
        resp.raise_for_status()

        devices = resp.json().get("devices", [])
        device = self._pick_device(devices, printer_name)
        if not device:
            raise RuntimeError("No printers found in cloud account")

        progress = device.get("mc_percent")
        if progress is None:
            progress = device.get("progress")
        try:
            progress = int(progress) if progress is not None else None
        except Exception:
            progress = None

        return {
            "name": device.get("name", "Unknown"),
            "model": device.get("dev_product_name") or device.get("dev_model_name") or "Unknown",
            "status": device.get("print_status", "UNKNOWN"),
            "progress": progress,
            "online": self._as_bool(device.get("online", False)),
            "updated": datetime.now().strftime("%H:%M:%S"),
        }

    def _finish_refresh_success(self, token, status, generation, migrated_plaintext, password):
        with self._state_lock:
            self._refresh_in_progress = False
            if generation != self._config_generation:
                return
            self.access_token = token
            self.password = password
            if migrated_plaintext:
                self._config_has_plaintext_password = False
            self._last_error_message = ""

        self._apply_status(status)

    def _finish_refresh_error(self, message, generation):
        with self._state_lock:
            self._refresh_in_progress = False
            if generation != self._config_generation:
                return

        self._set_quick_title("error")
        self.status_item.title = "Status: Error"
        self.progress_item.title = "Progress: -"
        self.updated_item.title = f"Last update: {datetime.now().strftime('%H:%M:%S')}"
        if message != self._last_error_message:
            rumps.notification("Bambu Status", "Cloud refresh failed", message)
            self._last_error_message = message

    def _apply_status(self, status):
        progress = status["progress"]
        self._set_quick_title(status["status"], progress)
        self.device_item.title = f"Printer: {status['name']}"
        self.model_item.title = f"Model: {status['model']}"
        self.status_item.title = f"Status: {status['status']}"
        self.progress_item.title = (
            f"Progress: {progress}%" if isinstance(progress, int) else "Progress: -"
        )
        self.online_item.title = f"Online: {'Yes' if status['online'] else 'No'}"
        self.updated_item.title = f"Last update: {status['updated']}"

    def refresh_now(self, _):
        if self._config_error_message or not self._can_attempt_refresh():
            self.configure()
            return
        self._refresh_async()

    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    BambuCloudStatusApp().run()
