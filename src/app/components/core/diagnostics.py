"""Persistent application diagnostics and uncaught-exception capture."""
import logging
import os
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGER = logging.getLogger("mixput")
_CONFIGURED = False


def log_path():
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "Mixput" / "logs" / "mixput.log"


def configure_diagnostics():
    """Write application errors and uncaught thread exceptions to a local log."""
    global _CONFIGURED
    if _CONFIGURED:
        return _LOGGER
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
        ))
        _LOGGER.setLevel(logging.INFO)
        _LOGGER.addHandler(handler)
        _LOGGER.propagate = False

        previous_hook = sys.excepthook

        def main_exception_hook(exc_type, exc_value, exc_traceback):
            _LOGGER.critical("Uncaught application exception", exc_info=(exc_type, exc_value, exc_traceback))
            previous_hook(exc_type, exc_value, exc_traceback)

        sys.excepthook = main_exception_hook

        if hasattr(threading, "excepthook"):
            previous_thread_hook = threading.excepthook

            def thread_exception_hook(args):
                _LOGGER.critical(
                    "Uncaught exception in thread %s",
                    args.thread.name if args.thread else "unknown",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
                previous_thread_hook(args)

            threading.excepthook = thread_exception_hook
        _CONFIGURED = True
        _LOGGER.info("Mixput diagnostics initialized. Log file: %s", path)
    except Exception:
        # Diagnostics must never prevent the application from starting.
        _LOGGER.exception("Could not initialize diagnostics at %s", path)
    return _LOGGER


def get_logger(name):
    configure_diagnostics()
    return logging.getLogger("mixput." + str(name))


def open_log_directory():
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    if platform.system() == "Windows":
        os.startfile(str(path.parent))
    elif platform.system() == "Darwin":
        import subprocess
        subprocess.Popen(["open", str(path.parent)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(path.parent)])
    return path
