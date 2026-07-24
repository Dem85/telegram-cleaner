import logging

from telegram_cleaner.constants import LOG_PATH


class Base64Filter(logging.Filter):
    """Filter out log messages containing base64-encoded image data.

    The openai._base_client logger dumps the full request JSON at DEBUG level,
    which includes the base64-encoded image data for vision API calls.
    This filter suppresses those messages to keep log files readable.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # Skip messages containing base64 image data URLs
        if "data:image/" in msg and ";base64," in msg:
            return False
        return True


def logging_configure() -> None:
    # remove all default basicConfig handlers
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    # write error/warning/info logs to file
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
    )

    # Suppress base64 image data from openai client debug logs
    openai_logger = logging.getLogger("openai._base_client")
    openai_logger.addFilter(Base64Filter())
