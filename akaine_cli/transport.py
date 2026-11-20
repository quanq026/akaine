"""ADB transport and per-operation session, consent and credential lifetime."""
from pathlib import Path
from . import catalogue
import getpass
import json
import re
import shlex
import struct
import subprocess
import sys
import threading
import time
import uuid
import warnings
from .contracts import (
    ACCOUNT_ERRORS,
    CREDENTIAL_LIMIT,
    CliError,
    DIRECTORY,
    DOMAIN_COMMANDS,
    LOG_TAGS,
    MAX_JSON,
    PRIVACY_URL,
    SERIAL,
    STAGING,
    TERMS_URL,
    UI_TOKEN,
    credential_bytes,
    domain_argument,
    mutation,
)
from .protocol import (
    guide_status,
    validate_advanced_guide,
    validate_domain_response,
    validate_identity,
    validate_ui,
)


_CONSENT_AUTHORITY = object()


class _TermsConsent:
    def __init__(self, target, authority):
        if authority is not _CONSENT_AUTHORITY:
            raise ValueError("Terms consent must come from the interactive prompt")
        self.scope = (target.package, target.environment)
        self.consumed = False
        self._lock = threading.Lock()

    def consume(self, target):
        with self._lock:
            if self.consumed or self.scope != (target.package, target.environment):
                return False
            self.consumed = True
            return True

    def close(self):
        with self._lock:
            self.consumed = True


class Deadline:
    def __init__(self, seconds, clock=time.monotonic):
        if not 1 <= seconds <= 30:
            raise CliError("ARGUMENT_ERROR", "--timeout must be between 1 and 30 seconds.")
        self.clock = clock
        self.end = clock() + seconds

    def remaining(self):
        value = self.end - self.clock()
        if value <= 0:
            raise CliError("TIMEOUT", "The operation deadline expired.")
        return value


class Adb:
    def __init__(self, executable, serial, runner=subprocess.run, *, target=STAGING):
        if not serial or not SERIAL.fullmatch(serial):
            raise CliError("INVALID_SERIAL", "Supply one explicit ADB serial without whitespace or shell characters.")
        self.executable, self.serial, self.runner = executable, serial, runner
        self._target = target

    @property
    def target(self):
        return self._target

    def call(self, arguments, timeout, data=None, allow_failure=False):
        try:
            result = self.runner(
                [self.executable, "-s", self.serial, *arguments], input=data,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            raise CliError("TIMEOUT", "ADB did not finish before the operation deadline.") from None
        except OSError:
            raise CliError("ADB_UNAVAILABLE", "Could not execute ADB; check --adb.") from None
        if result.returncode and not allow_failure:
            raise CliError("ADB_FAILED", "ADB or the app-private operation failed.")
        return result

    def shell(self, script, deadline, data=None, allow_failure=False):
        # ADB joins the remote argv into one shell command; quote the whole script.
        # shell v2 preserves the remote exit code; exec-out does not.
        return self.call(["shell", "-T", "run-as", self.target.package, "sh", "-c", shlex.quote(script)],
                         deadline.remaining(), data, allow_failure)

    def read(self, filename, deadline, optional=False):
        if filename not in ("bridge.json", "response.json"):
            raise ValueError("Only protocol JSON files may be read.")
        path = f"{DIRECTORY}/{filename}"
        # Fixed paths only. Never follow a bridge-directory or file symlink.
        script = (f"test -d {DIRECTORY} && test ! -L {DIRECTORY} && "
                  f"test -f {path} && test ! -L {path} && head -c {MAX_JSON + 1} {path}")
        result = self.shell(script, deadline, allow_failure=optional)
        if result.returncode:
            return None
        if len(result.stdout) > MAX_JSON:
            raise CliError("PROTOCOL_ERROR", "Bridge JSON exceeds the protocol limit.")
        try:
            value = json.loads(result.stdout)
        except (UnicodeDecodeError, ValueError):
            raise CliError("PROTOCOL_ERROR", "Bridge returned invalid JSON.") from None
        if not isinstance(value, dict):
            raise CliError("PROTOCOL_ERROR", "Bridge JSON must be an object.")
        return value


def redact_logs(raw):
    """Drop credential/account lines; scrub unlabelled tokens before any disk write."""
    sensitive = re.compile(
        r"\b(?:access[_-]?token|refresh[_-]?token|token|password|passwd|pwd|authorization|"
        r"cookie|api[_-]?key|secret|signature|email|username|user[_-]?(?:id|code|name)|"
        r"player[_-]?(?:id|code|name)|account[_-]?(?:id|name))[\"']?\s*[:=]", re.I)
    lines = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        normalized = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), line)
        normalized = re.sub(r"\\+([\"'])", r"\1", normalized)
        if sensitive.search(normalized):
            lines.append("[REDACTED sensitive diagnostic line]")
            continue
        line = re.sub(r"\bBearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", line, flags=re.I)
        line = re.sub(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                      "[REDACTED email]", line)
        line = re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}",
                      "[REDACTED token]", line)
        line = re.sub(r"(?<![A-Za-z0-9_+/-])[A-Za-z0-9_+/-]{32,}={0,2}(?![A-Za-z0-9_+/-])",
                      "[REDACTED token]", line)
        lines.append(line)
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def read_credentials(from_stdin=False):
    if not from_stdin:
        if not sys.stdin.isatty():
            raise CliError("CREDENTIAL_INPUT", "Use --credentials-stdin for a noninteractive credentials stream.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                return credential_bytes({"username": getpass.getpass("Username (hidden): ", stream=sys.stderr),
                                         "password": getpass.getpass("Password: ", stream=sys.stderr)})
        except (EOFError, getpass.GetPassWarning):
            raise CliError("CREDENTIAL_INPUT", "Hidden terminal input is unavailable; use --credentials-stdin.") from None
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    raw = stream.read(CREDENTIAL_LIMIT + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > CREDENTIAL_LIMIT:
        raise CliError("CREDENTIAL_INPUT", "Credentials JSON exceeds 512 bytes.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise CliError("CREDENTIAL_INPUT", "Credentials stdin must contain one valid JSON object.") from None
    return credential_bytes(value)


def confirm_terms(target=STAGING):
    """Create a one-use dispatch ticket only after a person's exact TTY reply."""
    if not sys.stdin.isatty():
        raise CliError("TERMS_INTERACTIVE_REQUIRED", "Run account terms-accept yourself in an interactive terminal.")
    sys.stderr.write("This command presses the game's native 'I Agree' for online-service Terms of Service and Privacy Policy.\n"
                     f"Terms of Service: {TERMS_URL}\nPrivacy Policy: {PRIVACY_URL}\n"
                     "Read both documents yourself. Acceptance records the game's normal consent preference.\n"
                     "It does not fill credentials or submit login. Type exactly AGREE to accept, or anything else to cancel: ")
    sys.stderr.flush()
    if sys.stdin.readline(64).rstrip("\r\n") != "AGREE":
        raise CliError("TERMS_NOT_ACCEPTED", "Legal agreement was not confirmed; no action was sent.")
    return _TermsConsent(target, _CONSENT_AUTHORITY)


def write_artifact(output, data):
    try:
        destination = Path(output).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        raise CliError("OUTPUT_FAILED", "The output path is invalid or unavailable.") from None
    if destination.exists():
        raise CliError("OUTPUT_EXISTS", "Choose a new output path; existing files are not overwritten.")
    if not destination.parent.is_dir():
        raise CliError("OUTPUT_DIRECTORY", "The output directory does not exist.")
    created = False
    try:
        with destination.open("xb") as stream:
            created = True
            stream.write(data)
    except OSError:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise CliError("OUTPUT_FAILED", "Could not write the requested output file.") from None
    return str(destination)


class Client:
    def __init__(self, adb, timeout=10, clock=time.monotonic, sleep=time.sleep):
        self.adb, self.deadline, self.sleep = adb, Deadline(timeout, clock), sleep
        self.timeout, self.clock = timeout, clock
        self.identity = None
        self.dispatched = False
        self.credential_owned = False

    @property
    def target(self):
        return self.adb.target

    @property
    def application_version(self):
        return (self.identity["application_version"] if self.target.environment == "production"
                else self.target.default_version)

    def inspect(self):
        metadata = self.adb.read("bridge.json", self.deadline)
        result = self.adb.call(["shell", "pidof", self.target.package], self.deadline.remaining())
        try:
            live_pid = result.stdout.decode("ascii").strip()
        except UnicodeDecodeError:
            raise CliError("STALE_BRIDGE", "The live app PID is invalid.") from None
        metadata = validate_identity(metadata, live_pid, target=self.target)
        fields = ("pid", "session", "application_version") if self.target.environment == "production" else ("pid", "session")
        if self.identity and any(metadata[key] != self.identity[key] for key in fields):
            raise CliError("BRIDGE_RESTARTED", f"The {self.target.environment} bridge restarted during the operation.")
        return metadata

    def publish_credentials(self, request_id, credentials):
        paths = tuple(f"{DIRECTORY}/{name}" for name in ("credential", "credential.tmp", "credential.inflight"))
        check = (f"test -d {DIRECTORY} && test ! -L {DIRECTORY} && " +
                 " && ".join(f"test ! -e {path} && test ! -L {path}" for path in paths))
        if self.adb.shell(check, self.deadline, allow_failure=True).returncode:
            raise CliError("CREDENTIAL_FILE_EXISTS", "Inspect the app-private credential files before another fill command.")
        username, password = credentials
        payload = bytearray(b"AKCRED1\n" + self.identity["session"].encode("ascii") + request_id.encode("ascii"))
        payload.extend(struct.pack("<HH", len(username), len(password)))
        payload.extend(username)
        payload.extend(password)
        self.credential_owned = True
        try:
            script = (f"umask 077; set -C; cat > {DIRECTORY}/credential.tmp && "
                      f"chmod 600 {DIRECTORY}/credential.tmp && mv -f {DIRECTORY}/credential.tmp {DIRECTORY}/credential")
            self.adb.shell(script, self.deadline, data=payload)
            self.inspect()
        finally:
            payload[:] = b"\0" * len(payload)

    def request(self, command, argument, credentials=None):
        if command not in self.identity["commands"]:
            raise CliError("UNSUPPORTED_COMMAND", f"This {self.target.environment} bridge does not support the requested command.")
        result = self.adb.call(["shell", "date", "+%s%3N"], self.deadline.remaining())
        if not re.fullmatch(rb"[1-9][0-9]{12}\s*", result.stdout):
            raise CliError("DEVICE_TIME", "Could not read the Android wall clock.")
        expires = int(result.stdout) + int(self.deadline.remaining() * 1000)
        request_id = uuid.uuid4().hex
        wire = f"AKCLI1 {request_id} {self.identity['session']} {expires} {command} {argument}\n".encode("ascii")
        if credentials is not None:
            self.publish_credentials(request_id, credentials)
        script = (f"umask 077; test ! -L {DIRECTORY}/request.tmp && "
                  f"test ! -L {DIRECTORY}/request && cat > {DIRECTORY}/request.tmp && "
                  f"chmod 600 {DIRECTORY}/request.tmp && mv -f {DIRECTORY}/request.tmp {DIRECTORY}/request")
        self.dispatched = mutation(command, argument)
        self.adb.shell(script, self.deadline, data=wire)
        while True:
            self.inspect()
            response = self.adb.read("response.json", self.deadline, optional=True)
            if response and response.get("request_id") == request_id:
                if (type(response.get("protocol")) is not int or response.get("protocol") != 1 or
                        response.get("session") != self.identity["session"] or
                        response.get("environment") != self.target.environment or response.get("command") != command or
                        type(response.get("ok")) is not bool or not isinstance(response.get("state"), dict)):
                    raise CliError("PROTOCOL_ERROR", "Response identity or structure does not match the request.")
                if response["ok"] and response.get("error") is not None:
                    raise CliError("PROTOCOL_ERROR", "Successful response contains an error.")
                if not response["ok"]:
                    error = response.get("error")
                    if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
                        raise CliError("PROTOCOL_ERROR", "Failed response is missing its error.")
                    if self.dispatched and error["code"] in ("ACTION_TIMEOUT", "SCENE_CHANGED", "STATE_CHANGED_AFTER_DISPATCH", "EXPIRED_AFTER_DISPATCH"):
                        error.update(outcome_unknown=True, automatic_retry=False)
                if response["ok"] and command == "category":
                    category = response["state"].get("category")
                    name = "mod" if argument == "8" else "variety"
                    if not isinstance(category, dict) or category.get("section") != int(argument) or category.get("name") != name:
                        raise CliError("PROTOCOL_ERROR", "Successful category response did not confirm the selected category.")
                ui = validate_ui(response["state"], self.application_version, target=self.target) if "ui" in response["state"] else None
                validate_advanced_guide(response["state"])
                if response["ok"] and command == "ui":
                    if ui is None:
                        raise CliError("PROTOCOL_ERROR", "UI response is missing native UI state.")
                    if argument != "list" and ui["context"] == argument.rsplit(".", 1)[1]:
                        raise CliError("PROTOCOL_ERROR", "UI activation did not confirm a changed action context.")
                if response["ok"] and command in DOMAIN_COMMANDS:
                    validate_domain_response(response["state"], command, argument, self.application_version, target=self.target)
                if "account" in response["state"]:
                    validate_domain_response(response["state"], "account", "status", self.application_version, target=self.target)
                if "customize" in response["state"] and (command != "customize" or not response["ok"]):
                    validate_domain_response(response["state"], "customize", "status", self.application_version, target=self.target)
                if "sync" in response["state"]:
                    validate_domain_response(response["state"], "sync", "status", self.application_version, target=self.target)
                if "bundle" in response["state"]:
                    validate_domain_response(response["state"], "bundle", "status", self.application_version, target=self.target)
                if not response["ok"] and response["error"]["code"] == "ACCOUNT_LOGIN_FAILED":
                    account = response["state"].get("account", {})
                    if (command != "account" or argument != "submit" or account.get("can_submit") is not True or account.get("blocked") is not False
                            or account.get("signed_in") is True or account.get("error_code") not in ACCOUNT_ERRORS
                            or account.get("error_code") == "unrecognized"):
                        raise CliError("PROTOCOL_ERROR", "Login failure lacks its exact recognized native error.")
                    response["error"].update(outcome_unknown=False, automatic_retry=False)
                self.inspect()
                return response
            self.sleep(min(0.1, self.deadline.remaining()))

    def customize_all(self):
        current = self.request("customize", "status")
        if not current["ok"]:
            return current
        value = current["state"]["customize"]
        if not value["available"] or not value["open"] or value["tab"] is None or value["download_required"]:
            raise CliError("CUSTOMIZE_UNAVAILABLE", "Open Customize before listing all items.")
        original = value["tab"]
        items = {original: value["items"]}
        for tab in ("title", "bgm", "scenery"):
            if tab == original:
                continue
            current = self.request("customize", "tab:" + tab)
            if not current["ok"]:
                return current
            items[tab] = current["state"]["customize"]["items"]
        restored = self.request("customize", "tab:" + original)
        if not restored["ok"]:
            return restored
        restored["catalogue"] = items
        return restored

    def execute(self, command, argument="none", output=None, options=None, credentials=None, *, terms_consent=None):
        self.deadline = Deadline(self.timeout, self.clock)
        self.dispatched = self.credential_owned = False
        locked = False
        result = None
        try:
            ui_command = command == "ui" and (argument == "list" or UI_TOKEN.fullmatch(argument))
            catalogue_command = command in ("song-catalogue", "pack-catalogue") and argument == "none"
            customize_all = command == "customize" and argument == "list-all"
            domain_command = domain_argument(command, argument) or customize_all
            guide_command = command == "guide" and argument in ("status", "next")
            if (((command, argument) not in (("status", "none"), ("category", "7"), ("category", "8"),
                                              ("screenshot", "none"), ("logs", "none")) and not ui_command and not catalogue_command and not domain_command and not guide_command) or
                    (command in ("screenshot", "logs") and output is None)):
                raise CliError("ARGUMENT_ERROR", "Unsupported command or argument.")
            if (command, argument) == ("account", "terms_accept"):
                if not isinstance(terms_consent, _TermsConsent) or not terms_consent.consume(self.target):
                    raise CliError("TERMS_INTERACTIVE_REQUIRED", "Run account terms-accept yourself and confirm AGREE in the terminal.")
            elif terms_consent is not None:
                raise CliError("ARGUMENT_ERROR", "Legal consent is accepted only by account terms-accept.")
            if (command, argument) == ("account", "fill"):
                if (not isinstance(credentials, tuple) or len(credentials) != 2
                        or any(not isinstance(value, bytearray) for value in credentials)):
                    raise CliError("CREDENTIAL_INPUT", "Account fill requires credentials from the private input path.")
                try:
                    checked = credential_bytes({"username": credentials[0].decode("utf-8"), "password": credentials[1].decode("utf-8")})
                    for value in checked:
                        value[:] = b"\0" * len(value)
                except UnicodeError:
                    raise CliError("CREDENTIAL_INPUT", "Credentials must contain valid UTF-8 text.") from None
            elif credentials is not None:
                raise CliError("CREDENTIAL_INPUT", "Credentials are accepted only by account fill.")
            self.identity = self.inspect()
            lock = self.adb.shell(f"mkdir -m 700 {DIRECTORY}/lock", self.deadline, allow_failure=True)
            if lock.returncode:
                raise CliError("LOCKED", "Another client owns the bridge lock; stale locks require manual inspection.")
            locked = True
            self.inspect()
            if command == "ui" and argument != "list":
                current = self.request("ui", "list")
                if not current["ok"]:
                    result = current
                    return result
                ui = validate_ui(current["state"], self.application_version, target=self.target)
                if argument.rsplit(".", 1)[1] != ui["context"]:
                    raise CliError("STALE_UI_CONTEXT", "Run ui list again; the action context changed.")
                if not any(action["token"] == argument and action["enabled"] for action in ui["actions"]):
                    raise CliError("UI_ACTION_UNAVAILABLE", "The requested action is not currently available.")
            if guide_command:
                current = self.request("ui", "list")
                if not current["ok"]:
                    result = current
                    return result
                guide = guide_status(current["state"], self.application_version, target=self.target)
                guide.update(operation=argument, performed=None)
                current["guide"] = guide
                if argument == "status" or guide["action"] is None:
                    result = current
                    return result
                fresh = self.request("ui", "list")
                if not fresh["ok"]:
                    result = fresh
                    return result
                confirmed = guide_status(fresh["state"], self.application_version, target=self.target)
                if fresh["state"]["ui"]["context"] != current["state"]["ui"]["context"]:
                    raise CliError("STALE_UI_CONTEXT", "The guide changed before dispatch; inspect guide status.")
                if confirmed != {key: guide[key] for key in confirmed}:
                    raise CliError("GUIDE_STATE_CHANGED", "Guide eligibility changed before dispatch; inspect guide status.")
                action = guide["action"]
                result = self.request(action["command"], action["argument"])
                after = guide_status(result["state"], self.application_version, target=self.target)
                after.update(operation=argument, attempted=action, performed=action if result["ok"] else None)
                after["may_continue_play"] = guide["may_continue_play"]
                after["effect"] = guide["effect"]
                result["guide"] = after
            elif catalogue_command:
                try:
                    installed = catalogue.load(self.adb, self.deadline, package=self.target.package,
                                               **({"application_version": self.application_version}
                                                  if self.target.environment == "production" else {}))
                    self.inspect()
                    result = catalogue.query(installed, "songs" if command == "song-catalogue" else "packs", options)
                except (ValueError, UnicodeError) as error:
                    raise CliError("CATALOGUE_ERROR", str(error)) from None
            elif customize_all:
                result = self.customize_all()
            elif command in ("status", "category", "ui") or domain_command:
                result = self.request(command, argument, credentials)
            elif command == "screenshot":
                data = self.adb.call(["exec-out", "screencap", "-p"], self.deadline.remaining()).stdout
                self.inspect()
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise CliError("SCREENSHOT_FAILED", "Android did not return a PNG screenshot.")
                result = {"ok": True, "command": command, "output": write_artifact(output, data)}
            elif command == "logs":
                data = self.adb.call(["logcat", "-d", "--pid=" + str(self.identity["pid"]),
                                      "-v", "threadtime", "-t", "2000", *LOG_TAGS], self.deadline.remaining()).stdout
                self.inspect()
                result = {"ok": True, "command": command, "output": write_artifact(output, redact_logs(data))}
            else:
                raise CliError("ARGUMENT_ERROR", "Unknown operation.")
        except CliError as error:
            if self.dispatched:
                error.details["outcome_unknown"] = True
                error.details["automatic_retry"] = False
            result = error.result()
        finally:
            if locked:
                try:
                    cleanup_script = f"rmdir {DIRECTORY}/lock"
                    if self.credential_owned:
                        cleanup_script = f"rm -f {DIRECTORY}/credential {DIRECTORY}/credential.tmp {DIRECTORY}/credential.inflight && " + cleanup_script
                    cleanup = self.adb.call(["shell", "-T", "run-as", self.target.package, "sh", "-c",
                                             shlex.quote(cleanup_script)], 3, allow_failure=True)
                    if cleanup.returncode:
                        raise CliError("LOCK_RELEASE_FAILED", "Could not release the bridge lock; inspect it manually.")
                except CliError:
                    if result is not None:
                        result["warning"] = ("Credential and bridge lock cleanup failed; inspect the app-private directory before another command."
                                             if self.credential_owned else "Bridge lock cleanup failed; inspect it manually before another command.")
            if isinstance(credentials, (tuple, list)):
                for value in credentials:
                    if isinstance(value, bytearray):
                        value[:] = b"\0" * len(value)
        return result
