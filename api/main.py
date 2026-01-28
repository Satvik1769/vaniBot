"""Battery Smart Voicebot API - Main Application."""
import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from contextlib import asynccontextmanager
import logging
import time

from .core.config import settings
from .core.database import init_db, close_db
from .routers import swaps, stations, subscriptions, dsk, drivers

from voice.orchestrator import VoiceOrchestrator
from voice.twilio_handler import TwilioHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global instances
orchestrator = VoiceOrchestrator()
twilio = TwilioHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting Battery Smart Voicebot API...")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")

    yield

    logger.info("Shutting down Battery Smart Voicebot API...")
    await close_db()
    logger.info("Database connections closed")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    Battery Smart Voicebot API for handling Tier-1 driver support queries.

    ## Features
    - **Swap History**: View past battery swaps and invoice explanations
    - **Station Finder**: Find nearest stations with real-time availability
    - **Subscriptions**: Check plan validity, renewals, and pricing
    - **DSK & Leaves**: Find service centers and manage leave requests

    ## Voice Integration
    Uses Twilio Media Streams + Deepgram STT/TTS + Rasa for voice bot.

    ## Languages
    Supports Hindi (hi), English (en), and Hinglish (hi-en) responses.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start_time)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred",
            "detail_hi": "Ek internal error hua"
        }
    )


# ── Health & Root ──────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "service": "battery-smart-voicebot-api"
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Battery Smart Voicebot API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


# ── Business Routers ──────────────────────────────────────────

app.include_router(drivers.router, prefix="/api/v1")
app.include_router(swaps.router, prefix="/api/v1")
app.include_router(stations.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")
app.include_router(dsk.router, prefix="/api/v1")


# ── Twilio TwiML – answers the incoming call ─────────────────
# Point your Twilio phone number's "A Call Comes In" webhook to:
#   POST https://<your-domain>/api/v1/twilio/voice
# This returns TwiML that tells Twilio to open a Media Stream
# WebSocket back to your server.
# ──────────────────────────────────────────────────────────────

@app.post("/api/v1/twilio/voice", tags=["Voice"])
async def twilio_voice_webhook(request: Request):
    """
    TwiML webhook – Twilio calls this when a call comes in.

    Returns TwiML instructing Twilio to:
    1. Open a bidirectional Media Stream to /ws/twilio-stream
    2. Pass the caller's phone number as a custom parameter
    """
    # Extract caller info from Twilio's POST body
    form = await request.form()
    caller = form.get("From", "")
    called = form.get("To", "")

    # Build the WebSocket URL dynamically from the incoming request
    host = request.headers.get("host", "localhost:8000")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/ws/twilio-stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="phone" value="{caller}" />
            <Parameter name="called" value="{called}" />
        </Stream>
    </Connect>
</Response>"""

    logger.info(f"Incoming call from {caller} -> streaming to {ws_url}")
    return Response(content=twiml, media_type="application/xml")


# ── Twilio Media Streams WebSocket ────────────────────────────
# Twilio opens this WebSocket after receiving the TwiML above.
# Audio flows bidirectionally: Twilio sends caller audio (mulaw),
# we send bot response audio (mulaw) back.
# ──────────────────────────────────────────────────────────────

async def _send_audio_to_twilio(
    websocket: WebSocket, stream_sid: str, pcm_8k: bytes
):
    """Send 8kHz PCM audio back to Twilio as mulaw in ~20ms chunks."""
    # Twilio expects ~20ms frames of mulaw
    # 8kHz * 1 byte (mulaw) * 0.02s = 160 bytes mulaw per frame
    # But we chunk by PCM first (8kHz * 2 bytes * 0.02s = 320 bytes PCM)
    pcm_chunk_size = 320  # 20ms at 8kHz, 16-bit
    for i in range(0, len(pcm_8k), pcm_chunk_size):
        chunk = pcm_8k[i: i + pcm_chunk_size]
        if not chunk:
            break
        msg = TwilioHandler.create_media_message(stream_sid, chunk)
        await websocket.send_text(json.dumps(msg))


@app.websocket("/ws/twilio-stream")
async def twilio_media_stream_ws(websocket: WebSocket):
    """
    Twilio Media Streams WebSocket endpoint.

    Event flow: connected -> start -> media* -> stop
    Audio: incoming mulaw 8kHz -> decode to PCM -> Deepgram -> Rasa -> TTS -> encode to mulaw -> send back
    """
    await websocket.accept()
    logger.info("Twilio Media Stream WebSocket accepted")

    session_id = None
    stream_sid = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event = data.get("event")

            if event == "connected":
                logger.info("Twilio stream connected")

            elif event == "start":
                call_info = twilio.parse_start_event(data)
                stream_sid = call_info.stream_sid
                session_id = call_info.call_sid or stream_sid

                logger.info(
                    f"Twilio stream started: stream_sid={stream_sid}, "
                    f"call_sid={call_info.call_sid}, "
                    f"phone={call_info.phone_number}"
                )

                # Start orchestrator session
                session = await orchestrator.start_session(
                    phone_number=call_info.phone_number,
                    session_id=session_id,
                    stream_sid=stream_sid,
                    call_sid=call_info.call_sid,
                    metadata=call_info.custom_parameters,
                )

                # Send greeting
                try:
                    greeting = await orchestrator._get_greeting(session)
                    if greeting:
                        greeting_pcm = await orchestrator.synthesize_for_twilio(
                            greeting, session.language
                        )
                        await _send_audio_to_twilio(
                            websocket, stream_sid, greeting_pcm
                        )
                        mark = TwilioHandler.create_mark_message(
                            stream_sid, "greeting_done"
                        )
                        await websocket.send_text(json.dumps(mark))
                        logger.info("Greeting audio sent")
                except Exception as e:
                    logger.error(f"Failed to send greeting: {e}", exc_info=True)

            elif event == "media":
                if not session_id:
                    continue

                payload = data.get("media", {}).get("payload", "")
                if not payload:
                    continue

                try:
                    # Decode mulaw -> 16-bit PCM at 8kHz
                    pcm_audio = TwilioHandler.decode_audio(payload)

                    # Process (buffer -> transcribe -> Rasa -> TTS)
                    response_pcm = await orchestrator.process_audio(
                        session_id, pcm_audio
                    )

                    if response_pcm and stream_sid:
                        await _send_audio_to_twilio(
                            websocket, stream_sid, response_pcm
                        )
                        session = orchestrator.get_session(session_id)
                        turn = session.turn_count if session else 0
                        mark = TwilioHandler.create_mark_message(
                            stream_sid, f"response_{turn}"
                        )
                        await websocket.send_text(json.dumps(mark))
                except Exception as e:
                    logger.error(f"Error processing media: {e}", exc_info=True)

            elif event == "mark":
                name = data.get("mark", {}).get("name", "")
                logger.debug(f"Mark received: {name}")

            elif event == "stop":
                reason = data.get("stop", {}).get("reason", "")
                logger.info(f"Twilio stream stopped: {reason}")
                if session_id:
                    await orchestrator.end_session(session_id, reason=reason or "hangup")
                break

    except WebSocketDisconnect:
        logger.info(f"Twilio WebSocket disconnected: session={session_id}")
        if session_id:
            try:
                await orchestrator.end_session(session_id, reason="disconnect")
            except Exception:
                pass
    except RuntimeError as e:
        # WebSocket closed unexpectedly (e.g., "WebSocket is not connected")
        logger.info(f"Twilio WebSocket closed: session={session_id}, reason={e}")
        if session_id:
            try:
                await orchestrator.end_session(session_id, reason="disconnect")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Twilio WebSocket error: {e}", exc_info=True)
        if session_id:
            try:
                await orchestrator.end_session(session_id, reason="error")
            except Exception:
                pass


# ── Twilio Status Callback ────────────────────────────────────

@app.post("/api/v1/twilio/status-callback", tags=["Voice"])
async def twilio_status_callback(request: Request):
    """Twilio call status callback webhook."""
    try:
        form = await request.form()
        result = await twilio.handle_status_callback(dict(form))
        return result
    except Exception as e:
        logger.error(f"Status callback error: {e}")
        return {"status": "error"}


# ── Voice Session REST Endpoints ──────────────────────────────

@app.post("/api/v1/voice/session/start", tags=["Voice"])
async def start_voice_session(phone_number: str):
    """Start a new voice session (via Twilio)."""
    return {
        "session_id": f"voice-{phone_number}-{int(time.time())}",
        "greeting": "Namaste! Battery Smart mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?",
        "greeting_en": "Hello! Welcome to Battery Smart. How can I help you today?",
        "language_detected": "hi-en"
    }


@app.post("/api/v1/voice/session/end", tags=["Voice"])
async def end_voice_session(session_id: str, resolution_status: str = "resolved"):
    """End a voice session."""
    return {
        "session_id": session_id,
        "status": "ended",
        "resolution_status": resolution_status,
        "farewell": "Dhanyavaad! Battery Smart ko choose karne ke liye shukriya.",
        "farewell_en": "Thank you for choosing Battery Smart. Have a great day!"
    }


@app.post("/api/v1/voice/outbound-call", tags=["Voice"])
async def make_outbound_call(
    request: Request,
    to_number: str,
    status_callback: str = None,
):
    """Initiate an outbound call via Twilio."""
    host = request.headers.get("host", "localhost:8000")
    scheme = "https" if request.url.scheme == "https" else "http"
    twiml_url = f"{scheme}://{host}/api/v1/twilio/voice"

    call_sid = await twilio.make_outbound_call(
        to_number=to_number,
        twiml_url=twiml_url,
        status_callback=status_callback,
    )
    if call_sid:
        return {"call_sid": call_sid, "status": "initiated"}
    return JSONResponse(status_code=500, content={"detail": "Failed to initiate call"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )