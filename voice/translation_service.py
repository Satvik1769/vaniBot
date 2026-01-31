"""Translation service for converting text to multiple languages.

Uses Google Cloud Translation API for translation to Romanian and Hindi.
"""
import os
import logging
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Result from translation service."""
    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    provider: str


class TranslationService:
    """Translation service using Google Cloud Translate.

    Supports translation to:
    - Romanian (ro)
    - Hindi (hi)
    """

    # Language codes for Google Translate
    LANGUAGE_CODES = {
        "romanian": "ro",
        "ro": "ro",
        "hindi": "hi",
        "hi": "hi",
        "english": "en",
        "en": "en",
        "hi-en": "en",  # Hinglish -> treat as English for source
    }

    def __init__(self):
        """Initialize translation service with Google Cloud Translate."""
        self._client = None
        self._initialized = False

    def _get_client(self):
        """Get or create Google Translate client."""
        if self._client is None:
            try:
                from google.cloud import translate_v2 as translate
                self._client = translate.Client()
                self._initialized = True
                logger.info("Google Translate client initialized")
            except Exception as e:
                logger.warning(f"Google Translate unavailable: {e}")
                self._initialized = False
        return self._client

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto"
    ) -> TranslationResult:
        """Translate text to target language using Google Translate."""
        if not text or not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=source_language,
                target_language=target_language,
                provider="none"
            )

        # Normalize language codes
        target_lang = self.LANGUAGE_CODES.get(target_language.lower(), target_language)
        source_lang = self.LANGUAGE_CODES.get(source_language.lower(), source_language) if source_language != "auto" else None

        try:
            client = self._get_client()
            if not client:
                return TranslationResult(
                    original_text=text,
                    translated_text=text,
                    source_language=source_language,
                    target_language=target_language,
                    provider="disabled"
                )

            # Call Google Translate API
            if source_lang:
                result = client.translate(
                    text,
                    target_language=target_lang,
                    source_language=source_lang
                )
            else:
                result = client.translate(
                    text,
                    target_language=target_lang
                )

            return TranslationResult(
                original_text=text,
                translated_text=result['translatedText'],
                source_language=result.get('detectedSourceLanguage', source_language),
                target_language=target_lang,
                provider="google_translate"
            )

        except Exception as e:
            logger.error(f"Google Translate error: {e}")
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_language=source_language,
                target_language=target_language,
                provider="failed"
            )

    async def translate_to_multiple(
        self,
        text: str,
        target_languages: list[str],
        source_language: str = "auto"
    ) -> Dict[str, TranslationResult]:
        """Translate text to multiple languages."""
        results = {}
        for lang in target_languages:
            results[lang] = await self.translate(text, lang, source_language)
        return results

    async def translate_to_romanian_and_hindi(
        self,
        text: str,
        source_language: str = "auto"
    ) -> Dict[str, TranslationResult]:
        """Translate text to both Romanian and Hindi."""
        return await self.translate_to_multiple(
            text,
            target_languages=["ro", "hi"],
            source_language=source_language
        )

    async def close(self):
        """Cleanup resources."""
        self._client = None


# Convenience function
async def translate_to_romanian_hindi(text: str, source_lang: str = "auto") -> Dict[str, str]:
    """Quick translation to Romanian and Hindi using Google Translate."""
    service = TranslationService()
    try:
        results = await service.translate_to_romanian_and_hindi(text, source_lang)
        return {
            "original": text,
            "romanian": results["ro"].translated_text,
            "hindi": results["hi"].translated_text,
        }
    finally:
        await service.close()