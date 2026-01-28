"""Voice orchestrator for integrating Deepgram with Rasa via Twilio Media Streams."""
import os
import asyncio
import uuid
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging
import httpx

from .deepgram_client import (
    DeepgramSTT,
    DeepgramTTS,
    DeepgramLanguageDetector,
    GoogleSTT,
    TranscriptionResult,
    TTSResult
)
from .twilio_handler import (
    TwilioHandler,
    strip_wav_header,
    resample_8k_to_16k,
    resample_16k_to_8k,
    TWILIO_SAMPLE_RATE,
)

logger = logging.getLogger(__name__)

RASA_URL = os.getenv("RASA_URL", "http://localhost:5005")

# Deepgram operates at 16kHz, Twilio at 8kHz
DEEPGRAM_SAMPLE_RATE = 16000

# Buffer ~2000ms of audio before sending to STT (allows capturing complete phrases)
MIN_BUFFER_DURATION_MS = 3000
CHUNK_DURATION_MS = 20  # Twilio sends ~20ms chunks

# Minimum confidence threshold - reject transcriptions below this
MIN_CONFIDENCE_THRESHOLD = 0.4


@dataclass
class VoiceSession:
    """Represents an active voice session."""
    session_id: str
    phone_number: str
    started_at: datetime = field(default_factory=datetime.now)
    language: str = "hi-en"
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    turn_count: int = 0
    last_activity: datetime = field(default_factory=datetime.now)
    sentiment_history: list = field(default_factory=list)
    confidence_history: list = field(default_factory=list)
    is_active: bool = True
    # Twilio-specific
    stream_sid: Optional[str] = None
    call_sid: Optional[str] = None
    audio_buffer: bytes = b""
    buffer_duration_ms: int = 0


class VoiceOrchestrator:
    """Orchestrates voice interaction using Google STT/TTS and Rasa via Twilio."""

    def __init__(
        self,
        deepgram_api_key: str = None,
        rasa_url: str = None,
        on_audio_output: Callable[[bytes], None] = None
    ):
        self.deepgram_api_key = deepgram_api_key or os.getenv("DEEPGRAM_API_KEY")
        self.rasa_url = rasa_url or RASA_URL

        # Use Google STT for Hindi/Hinglish (Deepgram kept for streaming if needed)
        self.stt = DeepgramSTT(self.deepgram_api_key)
        self.google_stt = GoogleSTT()
        self.tts = DeepgramTTS(self.deepgram_api_key)

        self.sessions: Dict[str, VoiceSession] = {}
        self.on_audio_output = on_audio_output

        # Callbacks
        self.on_transcription: Optional[Callable] = None
        self.on_response: Optional[Callable] = None
        self.on_handoff: Optional[Callable] = None

    async def start_session(
        self,
        phone_number: str,
        session_id: str = None,
        stream_sid: str = None,
        call_sid: str = None,
        metadata: Dict[str, Any] = None
    ) -> VoiceSession:
        """Start a new voice session."""
        session_id = session_id or f"voice-{phone_number}-{uuid.uuid4().hex[:8]}"

        session = VoiceSession(
            session_id=session_id,
            phone_number=phone_number,
            stream_sid=stream_sid,
            call_sid=call_sid,
        )
        self.sessions[session_id] = session

        # Notify Rasa of session start
        try:
            await self._send_to_rasa(
                session_id=session_id,
                message="/session_start",
                metadata={
                    "phone_number": phone_number,
                    "channel": "voice",
                    **(metadata or {})
                }
            )
        except Exception as e:
            logger.warning(f"Failed to send session_start to Rasa: {e}")

        logger.info(f"Started voice session: {session_id}")
        return session

    async def synthesize_for_twilio(self, text: str, language: str = "hi-en") -> bytes:
        """Synthesize text and return raw PCM at 8kHz (ready for Twilio encoding).

        Deepgram TTS produces 16kHz WAV. This strips the WAV header and
        downsamples to 8kHz linear PCM so TwilioHandler can encode to mulaw.
        """
        audio = await self.tts.synthesize(text, language)
        raw_pcm = strip_wav_header(audio.audio_data)
        return resample_16k_to_8k(raw_pcm)

    async def process_audio(
        self,
        session_id: str,
        pcm_audio_8k: bytes,
    ) -> Optional[bytes]:
        """Process incoming 8kHz PCM audio and return 8kHz PCM response.

        The caller (TwilioHandler) decodes mulaw -> PCM before calling this.
        This buffers audio, transcribes via Deepgram, sends to Rasa,
        synthesizes the response, and returns 8kHz PCM.
        """
        session = self.sessions.get(session_id)
        if not session or not session.is_active:
            logger.warning(f"Invalid or inactive session: {session_id}")
            return None

        session.last_activity = datetime.now()

        # Accumulate audio
        session.audio_buffer += pcm_audio_8k
        session.buffer_duration_ms += CHUNK_DURATION_MS

        if session.buffer_duration_ms < MIN_BUFFER_DURATION_MS:
            return None  # Keep buffering

        # Grab buffer and reset
        buffered = session.audio_buffer
        session.audio_buffer = b""
        session.buffer_duration_ms = 0

        # Upsample 8kHz -> 16kHz for Deepgram
        audio_16k = resample_8k_to_16k(buffered)

        # Transcribe
        transcript = await self._transcribe_audio(audio_16k, session.language)
        if not transcript or not transcript.text.strip():
            logger.debug(f"Empty transcript, skipping (buffer was {len(buffered)} bytes)")
            return None

        # Reject low-confidence transcriptions
        if transcript.confidence < MIN_CONFIDENCE_THRESHOLD:
            logger.info(f"Low confidence ({transcript.confidence:.2f}), ignoring: '{transcript.text}'")
            return None

        logger.info(f"Processing transcript: '{transcript.text}' (confidence: {transcript.confidence:.2f})")

        # Language detection
        detected_lang = DeepgramLanguageDetector.detect_from_text(transcript.text)
        if DeepgramLanguageDetector.should_switch_language(session.language, detected_lang):
            session.language = detected_lang
            logger.info(f"Language switched to: {detected_lang}")

        if self.on_transcription:
            await self.on_transcription(session_id, transcript)

        # Send to Rasa
        rasa_response = await self._send_to_rasa(
            session_id=session_id,
            message=transcript.text,
            metadata={
                "phone_number": session.phone_number,
                "language": session.language,
                "confidence": transcript.confidence,
            }
        )
        logger.info(f"Rasa response: {rasa_response}")

        session.turn_count += 1

        # Check handoff
        if self._should_handoff(rasa_response):
            if self.on_handoff:
                await self.on_handoff(session, rasa_response)
            return None

        # Get response text and synthesize
        response_text = self._extract_response_text(rasa_response)
        logger.info(f"Response text to synthesize: '{response_text}'")

        if response_text:
            if self.on_response:
                await self.on_response(session_id, response_text)
            audio = await self.synthesize_for_twilio(response_text, session.language)
            logger.info(f"Synthesized audio size: {len(audio)} bytes")
            return audio

        logger.warning("No response text from Rasa")
        return None

    async def stream_audio(
        self,
        session_id: str,
        on_transcript: Callable[[TranscriptionResult], None]
    ):
        """Start streaming audio transcription for a session."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        async def handle_transcript(result: TranscriptionResult):
            if result.is_final and result.text.strip():
                await on_transcript(result)
                response_audio = await self.process_transcription(
                    session_id, result.text
                )
                if response_audio and self.on_audio_output:
                    self.on_audio_output(response_audio)

        await self.stt.start_streaming(
            on_transcript=handle_transcript,
            language=session.language
        )

    async def send_audio_chunk(self, session_id: str, audio_chunk: bytes):
        """Send audio chunk for streaming transcription."""
        await self.stt.send_audio(audio_chunk)

    async def process_transcription(
        self,
        session_id: str,
        text: str
    ) -> Optional[bytes]:
        """Process text transcription and return 8kHz PCM response audio."""
        session = self.sessions.get(session_id)
        if not session or not session.is_active:
            return None

        session.last_activity = datetime.now()
        session.turn_count += 1

        rasa_response = await self._send_to_rasa(
            session_id=session_id,
            message=text,
            metadata={
                "phone_number": session.phone_number,
                "language": session.language,
            }
        )

        if self._should_handoff(rasa_response):
            if self.on_handoff:
                await self.on_handoff(session, rasa_response)
            return None

        response_text = self._extract_response_text(rasa_response)
        if response_text:
            return await self.synthesize_for_twilio(response_text, session.language)
        return None

    async def end_session(
        self,
        session_id: str,
        reason: str = "completed"
    ):
        """End a voice session."""
        session = self.sessions.get(session_id)
        if not session:
            return

        session.is_active = False

        await self.stt.stop_streaming()

        try:
            await self._send_to_rasa(
                session_id=session_id,
                message="/session_end",
                metadata={"reason": reason}
            )
        except Exception as e:
            logger.warning(f"Failed to send session_end to Rasa: {e}")

        del self.sessions[session_id]
        logger.info(f"Ended voice session: {session_id} (reason={reason})")

    # ── Internal helpers ────────────────────────────────────────

    async def _transcribe_audio(
        self,
        audio_data: bytes,
        language: str
    ) -> Optional[TranscriptionResult]:
        """Transcribe audio using Google Cloud Speech-to-Text."""
        try:
            result = await self.google_stt.transcribe(
                audio_data=audio_data,
                language=language,
                sample_rate=16000,
            )

            if result:
                logger.info(f"Google STT transcript: '{result.text}' (confidence: {result.confidence:.2f})")
                return result
            else:
                logger.debug("Google STT returned no results")
        except Exception as e:
            logger.error(f"Transcription error: {e}")

        return None

    async def _send_to_rasa(
        self,
        session_id: str,
        message: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Send message to Rasa and get response."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.rasa_url}/webhooks/rest/webhook",
                    json={
                        "sender": session_id,
                        "message": message,
                        "metadata": metadata or {}
                    }
                )
                if response.status_code == 200:
                    return {"responses": response.json()}
                else:
                    logger.error(f"Rasa error: {response.status_code}")
                    return {"responses": []}
        except Exception as e:
            logger.error(f"Error sending to Rasa: {e}")
            return {"responses": []}

    async def _get_greeting(self, session: VoiceSession) -> str:
        """Get greeting message for new session."""
        if session.driver_name:
            return f"Namaste {session.driver_name}! Battery Smart mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?"
        return "Namaste! Battery Smart mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?"

    def _should_handoff(self, rasa_response: Dict[str, Any]) -> bool:
        """Check if response indicates handoff needed."""
        responses = rasa_response.get("responses", [])
        for resp in responses:
            if resp.get("custom", {}).get("action") == "handoff":
                return True
            text = resp.get("text", "").lower()
            if "agent se connect" in text or "transfer" in text:
                return True
        return False

    def _extract_response_text(self, rasa_response: Dict[str, Any]) -> str:
        """Extract first response text from Rasa response (for voice, only use first)."""
        responses = rasa_response.get("responses", [])
        for r in responses:
            if "text" in r and r["text"].strip():
                return r["text"]
        return ""

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)

    def get_active_sessions(self) -> Dict[str, VoiceSession]:
        """Get all active sessions."""
        return {
            sid: s for sid, s in self.sessions.items() if s.is_active
        }