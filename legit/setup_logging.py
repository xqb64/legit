import logging
import sys
from pathlib import Path

LOG_LEVEL = logging.DEBUG
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  →  %(message)s"


def setup_logging(
    level: int | str = LOG_LEVEL,
    log_file: str | Path | None = None,
) -> None:
    if isinstance(level, str):
        level = level.upper()

    root = logging.getLogger()
    root.setLevel(level)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        file_handler.setLevel(level)

        formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(formatter)

        if not any(
            isinstance(h, logging.FileHandler)
            and h.baseFilename == str(log_path.resolve())
            for h in root.handlers
        ):
            root.addHandler(file_handler)

    if not root.handlers:
        logging.basicConfig(
            level=level,
            format=LOG_FORMAT,
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
