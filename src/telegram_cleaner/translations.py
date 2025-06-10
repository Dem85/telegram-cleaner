from telegram_cleaner.config import get_config
from telegram_cleaner.constants import TRANSLATIONS


def _(key: str, **kwargs) -> str:
    """Get translation for key."""
    config = get_config()
    translation = TRANSLATIONS.get(config.LANG, {}).get(key)

    # fallback -> english
    if translation is None:
        translation = TRANSLATIONS.get("en", {}).get(key)

    if kwargs:
        try:
            translation = translation.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return translation
