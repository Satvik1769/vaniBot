"""Deepgram client for Speech-to-Text + Google Cloud TTS for Text-to-Speech."""
import os
import asyncio
import io
from typing import Optional, AsyncGenerator, Callable
from dataclasses import dataclass
import logging
from dotenv import load_dotenv
load_dotenv()


from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    PrerecordedOptions,
)

logger = logging.getLogger(__name__)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


@dataclass
class TranscriptionResult:
    """Result from speech-to-text transcription."""
    text: str
    confidence: float
    is_final: bool
    language: str
    words: list


@dataclass
class TTSResult:
    """Result from text-to-speech synthesis."""
    audio_data: bytes
    content_type: str
    duration_ms: Optional[int] = None


class DeepgramSTT:
    """Deepgram Speech-to-Text client with streaming and batch support."""

    # Domain-specific vocabulary for speech adaptation (similar to Google STT)
    DOMAIN_PHRASES = [
        "Battery Smart", "battery swap", "swap station", "charging station",
        "subscription", "monthly plan", "nearest station",
        "kahan hai", "batao", "dikhao", "chahiye", "kitna", "kitni",
        "namaste", "dhanyawad",
    ]

    def __init__(self, api_key: str = None):
        self.api_key = api_key or DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError("Deepgram API key is required")

        config = DeepgramClientOptions(options={"keepalive": "true"})
        self.client = DeepgramClient(self.api_key, config)
        self.connection = None
        self.transcript_callback: Optional[Callable] = None

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "hi",
        sample_rate: int = 16000,
    ) -> Optional[TranscriptionResult]:
        """Transcribe audio using Deepgram REST API (non-streaming).

        Args:
            audio_data: Raw PCM audio bytes
            language: Language code (hi, en, hi-en for multilingual)
            sample_rate: Audio sample rate in Hz

        Returns:
            TranscriptionResult or None if transcription failed
        """
        try:
            # Map language codes - avoid "multi" as it doesn't work well for short audio
            lang_map = {
                "hi": "hi",
                "hi-en": "hi",  # Use Hindi for Hinglish (better than multi)
                "en": "en",
            }
            dg_language = lang_map.get(language, "hi")

            options = PrerecordedOptions(
                model="nova-2",
                language=dg_language,
                smart_format=True,
                punctuate=True,
                diarize=False,
                keywords=self.DOMAIN_PHRASES,
                encoding="linear16",
                channels=1,
                sample_rate=sample_rate,
            )

            # Use the prerecorded API
            source = {"buffer": audio_data, "mimetype": "audio/raw"}
            response = await self.client.listen.asyncrest.v("1").transcribe_file(
                source, options
            )

            if response and response.results and response.results.channels:
                channel = response.results.channels[0]
                if channel.alternatives:
                    alt = channel.alternatives[0]

                    # Extract words if available
                    words = []
                    if hasattr(alt, 'words') and alt.words:
                        words = [{
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "confidence": w.confidence
                        } for w in alt.words]

                    detected_lang = (
                        response.results.channels[0].detected_language
                        if hasattr(response.results.channels[0], 'detected_language')
                        else language
                    )

                    return TranscriptionResult(
                        text=alt.transcript,
                        confidence=alt.confidence,
                        is_final=True,
                        language=detected_lang or language,
                        words=words,
                    )

            return None

        except Exception as e:
            logger.error(f"Deepgram transcribe error: {e}")
            return None

    async def start_streaming(
        self,
        on_transcript: Callable[[TranscriptionResult], None],
        language: str = "hi",
        model: str = "nova-2",
        interim_results: bool = True
    ):
        """Start streaming transcription."""
        self.transcript_callback = on_transcript

        options = LiveOptions(
            model=model,
            language=language,
            smart_format=True,
            interim_results=interim_results,
            utterance_end_ms=1500,
            vad_events=True,
            endpointing=300,
            encoding="linear16",
            channels=1,
            sample_rate=16000,
        )

        self.connection = self.client.listen.asynclive.v("1")

        # Set up event handlers
        self.connection.on(LiveTranscriptionEvents.Open, self._on_open)
        self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
        self.connection.on(LiveTranscriptionEvents.Close, self._on_close)

        await self.connection.start(options)
        logger.info("Deepgram streaming started")

    async def send_audio(self, audio_data: bytes):
        """Send audio chunk for transcription."""
        if self.connection:
            await self.connection.send(audio_data)

    async def stop_streaming(self):
        """Stop streaming transcription."""
        if self.connection:
            await self.connection.finish()
            self.connection = None
            logger.info("Deepgram streaming stopped")

    async def _on_open(self, *args, **kwargs):
        logger.debug("Deepgram connection opened")

    async def _on_transcript(self, *args, **kwargs):
        result = kwargs.get("result") or (args[1] if len(args) > 1 else None)
        if not result:
            return

        try:
            channel = result.channel
            alternatives = channel.alternatives

            if alternatives:
                alt = alternatives[0]
                transcript = alt.transcript

                if transcript:
                    transcription_result = TranscriptionResult(
                        text=transcript,
                        confidence=alt.confidence,
                        is_final=result.is_final,
                        language=result.channel.detected_language or "hi",
                        words=[{
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "confidence": w.confidence
                        } for w in (alt.words or [])]
                    )

                    if self.transcript_callback:
                        await self.transcript_callback(transcription_result)

        except Exception as e:
            logger.error(f"Error processing transcript: {e}")

    async def _on_error(self, *args, **kwargs):
        error = kwargs.get("error") or (args[1] if len(args) > 1 else None)
        logger.error(f"Deepgram error: {error}")

    async def _on_close(self, *args, **kwargs):
        logger.debug("Deepgram connection closed")


class GoogleSTT:
    """Google Cloud Speech-to-Text client with Hindi support and domain biasing."""

    # Language code mapping
    LANGUAGES = {
        "hi": "hi-IN",
        "hi-en": "hi-IN",  # Hinglish -> use Hindi
        "en": "en-IN",
    }

    # Domain-specific vocabulary for speech adaptation
    # These terms get boosted during recognition
    DOMAIN_PHRASES = [
        # Core business terms
        "Battery Smart",
        "battery swap",
        "swap station",
        "charging station",
        "subscription",
        "monthly plan",
        "nearest station",

        # Hindi terms (Romanized)
        "kahan hai",
        "batao",
        "dikhao",
        "chahiye",
        "kitna",
        "kitni",
        "namaste",
        "dhanyawad",

        # Location terms
        "Delhi",
        "Mumbai",
        "Bangalore",
        "Hyderabad",
        "Pune",
        "Gurgaon",
        "Noida",

        # Action phrases
        "find station",
        "book swap",
        "check balance",
        "station dikha do",
        "nearest swap kahan hai",
        "battery kaise swap kare",
    ]

    def __init__(self):
        from google.cloud import speech_v1 as speech
        self._speech = speech
        self.client = speech.SpeechAsyncClient()
        self._speech_context = self._build_speech_context()

    def _build_speech_context(self):
        """Build speech adaptation context with boosted phrases."""
        speech = self._speech

        # Create speech context with domain phrases
        # Boost value: 1-20, higher = more likely to recognize
        return speech.SpeechContext(
            phrases=self.DOMAIN_PHRASES,
            boost=15.0  # Strong boost for domain terms
        )

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "hi-en",
        sample_rate: int = 16000,
    ) -> Optional[TranscriptionResult]:
        """Transcribe audio to text with domain biasing."""
        speech = self._speech

        lang_code = self.LANGUAGES.get(language, "hi-IN")

        # For Hinglish, add English as alternative language for code-switching
        alternative_languages = []
        if language == "hi-en":
            alternative_languages = ["en-IN"]

        # Build recognition config with speech adaptation
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=lang_code,
            alternative_language_codes=alternative_languages,
            enable_automatic_punctuation=True,
            model="latest_long",
            # Enable word-level confidence
            enable_word_confidence=True,
            # Enable spoken punctuation for natural speech
            enable_spoken_punctuation=False,
            # Add domain-specific speech context
            speech_contexts=[self._speech_context],
            # Use enhanced model for telephony if available
            use_enhanced=True,
        )

        audio = speech.RecognitionAudio(content=audio_data)

        try:
            response = await self.client.recognize(config=config, audio=audio)

            if response.results:
                result = response.results[0]
                if result.alternatives:
                    alt = result.alternatives[0]

                    # Extract word-level info if available
                    words = []
                    if hasattr(alt, 'words') and alt.words:
                        words = [{
                            "word": w.word,
                            "confidence": w.confidence,
                            "start": w.start_time.total_seconds() if hasattr(w, 'start_time') else 0,
                            "end": w.end_time.total_seconds() if hasattr(w, 'end_time') else 0,
                        } for w in alt.words]

                    return TranscriptionResult(
                        text=alt.transcript,
                        confidence=alt.confidence,
                        is_final=True,
                        language=language,
                        words=words,
                    )
            return None
        except Exception as e:
            logger.error(f"Google STT error: {e}")
            return None

    def add_domain_phrases(self, phrases: list[str]):
        """Add additional domain phrases for recognition boost."""
        self.DOMAIN_PHRASES.extend(phrases)
        self._speech_context = self._build_speech_context()


class GoogleTTS:
    """Google Cloud Text-to-Speech client with Hindi support."""

    # Language -> (language_code, voice_name) mapping
    VOICES = {
        "hi":    ("hi-IN", "hi-IN-Wavenet-A"),    # Hindi female
        "hi-en": ("hi-IN", "hi-IN-Wavenet-A"),    # Hinglish -> use Hindi voice
        "en":    ("en-IN", "en-IN-Wavenet-A"),     # English Indian accent female
    }

    def __init__(self):
        from google.cloud import texttospeech_v1 as tts
        self._tts = tts
        self.client = tts.TextToSpeechAsyncClient()

    async def synthesize(
        self,
        text: str,
        language: str = "hi-en",
    ) -> TTSResult:
        """Synthesize text to 16kHz 16-bit linear PCM (WAV)."""
        tts = self._tts

        lang_code, voice_name = self.VOICES.get(language, self.VOICES["hi-en"])

        request = tts.SynthesizeSpeechRequest(
            input=tts.SynthesisInput(text=text),
            voice=tts.VoiceSelectionParams(
                language_code=lang_code,
                name=voice_name,
            ),
            audio_config=tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
            ),
        )

        try:
            response = await self.client.synthesize_speech(request=request)
            return TTSResult(
                audio_data=response.audio_content,
                content_type="audio/wav",
            )
        except Exception as e:
            logger.error(f"Google TTS error: {e}")
            raise


# Keep DeepgramTTS as a fallback for English-only use cases
class DeepgramTTS:
    """Deepgram Text-to-Speech client (English/Spanish only)."""

    VOICES = {
        "en": "aura-asteria-en",
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError("Deepgram API key is required")
        self.client = DeepgramClient(self.api_key)
        # Google TTS for Hindi/Hinglish
        self.google_tts = GoogleTTS()

    async def synthesize(
        self,
        text: str,
        language: str = "hi-en",
        model: str = None
    ) -> TTSResult:
        """Synthesize text to speech.

        Uses Google Cloud TTS for Hindi/Hinglish, Deepgram for English.
        """
        # Use Google TTS for Hindi and Hinglish
        if language in ("hi", "hi-en"):
            return await self.google_tts.synthesize(text, language)

        # Use Deepgram for English
        voice = model or self.VOICES.get(language, "aura-asteria-en")

        options = {
            "model": voice,
            "encoding": "linear16",
            "sample_rate": 16000,
            "container": "wav",
        }

        try:
            response = await self.client.speak.asyncrest.v("1").stream_memory(
                {"text": text},
                options,
            )

            return TTSResult(
                audio_data=response.stream.getvalue() if hasattr(response, 'stream') else response,
                content_type="audio/wav"
            )

        except Exception as e:
            logger.error(f"Deepgram TTS error: {e}")
            raise


class DeepgramLanguageDetector:
    """Detect language from text or audio."""

    # Common Hindi words (Romanized)
    HINDI_MARKERS = {
        "hai", "hain", "kya", "kahan", "kaise", "kyun", "mera", "meri",
        "aapka", "aapki", "batao", "dikhao", "chahiye", "karo", "karein",
        "nahi", "haan", "theek", "achha", "bahut", "bohot", "abhi",
        "kal", "aaj", "yahan", "wahan", "kaun", "kab", "kitna", "kitni"
    }

    # Common English words
    ENGLISH_MARKERS = {
        "the", "is", "are", "was", "were", "have", "has", "can", "could",
        "would", "should", "will", "what", "where", "when", "how", "why",
        "please", "help", "need", "want", "show", "check", "find"
    }

    @classmethod
    def detect_from_text(cls, text: str) -> str:
        """Detect language from text."""
        if not text:
            return "hi-en"

        # Check for Devanagari script
        has_devanagari = any('\u0900' <= c <= '\u097F' for c in text)
        if has_devanagari:
            return "hi"

        # Count marker words
        words = set(text.lower().split())
        hindi_count = len(words & cls.HINDI_MARKERS)
        english_count = len(words & cls.ENGLISH_MARKERS)

        total_markers = hindi_count + english_count
        if total_markers == 0:
            return "hi-en"  # Default to Hinglish

        # Determine language based on ratio
        hindi_ratio = hindi_count / total_markers

        if hindi_ratio > 0.7:
            return "hi"
        elif hindi_ratio < 0.3:
            return "en"
        else:
            return "hi-en"

    @classmethod
    def should_switch_language(cls, current: str, detected: str) -> bool:
        """Check if language should be switched."""
        # Don't switch if current is Hinglish (flexible)
        if current == "hi-en":
            return False

        # Switch if detected is significantly different
        if current == "hi" and detected == "en":
            return True
        if current == "en" and detected == "hi":
            return True

        return False