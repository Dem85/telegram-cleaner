from telegram_cleaner import constants


class Translator:
    """Translate text."""

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang

    def __call__(self, key: str, **kwargs: dict[str, str]) -> str:
        """Get translation for key and format with kwargs."""
        translation = constants.TRANSLATIONS.get(self.lang, {}).get(key)
        # fallback -> english
        if translation is None:
            translation = constants.TRANSLATIONS.get("en", {}).get(key)
        if kwargs:
            translation = translation.format(**kwargs)
        return translation
