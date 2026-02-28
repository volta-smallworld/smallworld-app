"""
Centralized logging config for smallworld.
"""

import logging
import sys
import time
from contextlib import contextmanager

# Color codes for terminal
GRAY = "\033[90m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"

LEVEL_COLORS = {
    "DEBUG": GRAY,
    "INFO": GREEN,
    "WARNING": YELLOW,
    "ERROR": RED,
    "CRITICAL": RED + BOLD,
}


class ColorFormatter(logging.Formatter):
    def format(self, record):
        level = record.levelname
        color = LEVEL_COLORS.get(level, "")
        module = record.name.replace("smallworld.", "")

        timestamp = self.formatTime(record, "%H:%M:%S")
        msg = record.getMessage()

        return f"{GRAY}{timestamp}{RESET} {color}{level:>7}{RESET} {CYAN}{module:<20}{RESET} {msg}"


def setup_logging(level=logging.INFO):
    """Set up root logger with colored console output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter())

    root = logging.getLogger("smallworld")
    root.setLevel(level)
    root.handlers = [handler]
    root.propagate = False

    return root


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the smallworld namespace."""
    return logging.getLogger(f"smallworld.{name}")


@contextmanager
def log_phase(logger: logging.Logger, phase_name: str):
    """Context manager that logs phase start/end with elapsed time."""
    logger.info(f"{BOLD}▶ {phase_name}{RESET}")
    start = time.time()
    try:
        yield
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"✗ {phase_name} failed after {elapsed:.1f}s: {e}")
        raise
    else:
        elapsed = time.time() - start
        logger.info(f"✓ {phase_name} completed in {BOLD}{elapsed:.1f}s{RESET}")
