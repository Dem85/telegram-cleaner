import logging

from telegram_cleaner.constants import LOG_PATH


def logging_configure() -> None:
    # remove all default basicConfig handlers
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    # write error/warning/info logs to file
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
    )
