import logging
import sys
from pathlib import Path

LOG_LEVEL = logging.DEBUG  # Set to DEBUG for testing
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  →  %(message)s"


def setup_logging(
    level: int | str = LOG_LEVEL,
    log_file: str | Path | None = None,
) -> None:
    """
    Configures logging. When run under pytest, it "cooperatively" adds
    a file handler instead of trying to reconfigure the root logger.
    """
    if isinstance(level, str):
        level = level.upper()

    # Get the root logger
    root = logging.getLogger()
    root.setLevel(level)

    # If a log file is specified, create and add a file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create your specific file handler
        file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        file_handler.setLevel(level)

        # Create a formatter
        formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(formatter)

        # Add the handler ONLY if a similar one doesn't already exist
        # This prevents adding duplicate handlers on re-imports.
        if not any(
            isinstance(h, logging.FileHandler)
            and h.baseFilename == str(log_path.resolve())
            for h in root.handlers
        ):
            root.addHandler(file_handler)

    # For standalone runs (not pytest), ensure a basic console handler exists
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format=LOG_FORMAT,
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
