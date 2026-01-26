"""Voice orchestrator for integrating Deepgram with Rasa."""
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
    TranscriptionResult,
    TTSResult
)

logger = logging.getLogger(__name__)

RASA_URL = os.getenv("RASA_URL", "http://localhost:5005")


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


class VoiceOrchestrator:
    """Orchestrates voice interaction between Deepgram and Rasa."""

    def __init__(
        self,
        deepgram_api_key: str = None,
        rasa_url: str = None,
        on_audio_output: Callable[[bytes], None] = None
    ):
        self.deepgram_api_key = deepgram_api_key or os.getenv("DEEPGRAM_API_KEY")
        self.rasa_url = rasa_url or RASA_URL

        self.stt = DeepgramSTT(self.deepgram_api_key)
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
        metadata: Dict[str, Any] = None
    ) -> VoiceSession:
        """Start a new voice session."""
        session_id = session_id or f"voice-{phone_number}-{uuid.uuid4().hex[:8]}"

        session = VoiceSession(
            session_id=session_id,
            phone_number=phone_number
        )
        self.sessions[session_id] = session

        # Send session start to Rasa
        await self._send_to_rasa(
            session_id=session_id,
            message="/session_start",
            metadata={
                "phone_number": phone_number,
                "channel": "voice",
                **(metadata or {})
            }
        )

        # Get initial greeting
        greeting = await self._get_greeting(session)

        # Synthesize greeting
        if greeting:
            audio = await self.tts.synthesize(greeting, session.language)
            if self.on_audio_output:
                self.on_audio_output(audio.audio_data)

        logger.info(f"Started voice session: {session_id}")
        return session

    async def process_audio(
        self,
        session_id: str,
        audio_data: bytes
    ) -> Optional[bytes]:
        """Process incoming audio and return response audio."""
        session = self.sessions.get(session_id)
        if not session or not session.is_active:
            logger.warning(f"Invalid or inactive session: {session_id}")
            return None

        session.last_activity = datetime.now()

        # Transcribe audio
        transcript = await self._transcribe_audio(audio_data, session.language)

        if not transcript or not transcript.text.strip():
            return None

        # Update language if detected differently
        detected_lang = DeepgramLanguageDetector.detect_from_text(transcript.text)
        if DeepgramLanguageDetector.should_switch_language(session.language, detected_lang):
            session.language = detected_lang
            logger.info(f"Language switched to: {detected_lang}")

        # Callback for transcription
        if self.on_transcription:
            await self.on_transcription(session_id, transcript)

        # Send to Rasa and get response
        rasa_response = await self._send_to_rasa(
            session_id=session_id,
            message=transcript.text,
            metadata={
                "phone_number": session.phone_number,
                "language": session.language,
                "confidence": transcript.confidence
            }
        )

        session.turn_count += 1

        # Check for handoff
        if self._should_handoff(rasa_response):
            if self.on_handoff:
                await self.on_handoff(session, rasa_response)
            return None

        # Get bot response text
        response_text = self._extract_response_text(rasa_response)

        if response_text:
            # Callback for response
            if self.on_response:
                await self.on_response(session_id, response_text)

            # Synthesize response
            audio = await self.tts.synthesize(response_text, session.language)
            return audio.audio_data

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

                # Process the transcript
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
        """Process a text transcription and return response audio."""
        session = self.sessions.get(session_id)
        if not session or not session.is_active:
            return None

        session.last_activity = datetime.now()
        session.turn_count += 1

        # Send to Rasa
        rasa_response = await self._send_to_rasa(
            session_id=session_id,
            message=text,
            metadata={
                "phone_number": session.phone_number,
                "language": session.language
            }
        )

        # Check for handoff
        if self._should_handoff(rasa_response):
            if self.on_handoff:
                await self.on_handoff(session, rasa_response)
            return None

        # Get response text
        response_text = self._extract_response_text(rasa_response)

        if response_text:
            # Synthesize response
            audio = await self.tts.synthesize(response_text, session.language)
            return audio.audio_data

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

        # Stop streaming if active
        await self.stt.stop_streaming()

        # Send session end to Rasa
        await self._send_to_rasa(
            session_id=session_id,
            message="/session_end",
            metadata={"reason": reason}
        )

        # Get farewell
        farewell = "Dhanyavaad! Battery Smart ko choose karne ke liye shukriya."
        audio = await self.tts.synthesize(farewell, session.language)

        if self.on_audio_output:
            self.on_audio_output(audio.audio_data)

        # Clean up
        del self.sessions[session_id]
        logger.info(f"Ended voice session: {session_id}")

    async def _transcribe_audio(
        self,
        audio_data: bytes,
        language: str
    ) -> Optional[TranscriptionResult]:
        """Transcribe audio using Deepgram."""
        try:
            # Use non-streaming transcription for simple audio
            from deepgram import PrerecordedOptions

            client = self.stt.client
            options = PrerecordedOptions(
                model="nova-2",
                language=language if language != "hi-en" else "hi",
                smart_format=True,
                punctuate=True,
            )

            response = await client.listen.asyncrest.v("1").transcribe_file(
                {"buffer": audio_data},
                options
            )

            results = response.results
            if results and results.channels:
                alt = results.channels[0].alternatives[0]
                return TranscriptionResult(
                    text=alt.transcript,
                    confidence=alt.confidence,
                    is_final=True,
                    language=language,
                    words=[]
                )

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
        else:
            return "Namaste! Battery Smart mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?"

    def _should_handoff(self, rasa_response: Dict[str, Any]) -> bool:
        """Check if response indicates handoff needed."""
        responses = rasa_response.get("responses", [])
        for resp in responses:
            # Check for handoff custom action response
            if resp.get("custom", {}).get("action") == "handoff":
                return True
            # Check for handoff utterance
            if "agent se connect" in resp.get("text", "").lower():
                return True
            if "transfer" in resp.get("text", "").lower():
                return True
        return False

    def _extract_response_text(self, rasa_response: Dict[str, Any]) -> str:
        """Extract response text from Rasa response."""
        responses = rasa_response.get("responses", [])
        texts = []
        for resp in responses:
            if "text" in resp:
                texts.append(resp["text"])
        return " ".join(texts)

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get session by ID."""
        return self.sessions.get(session_id)

    def get_active_sessions(self) -> Dict[str, VoiceSession]:
        """Get all active sessions."""
        return {
            sid: session
            for sid, session in self.sessions.items()
            if session.is_active
        }