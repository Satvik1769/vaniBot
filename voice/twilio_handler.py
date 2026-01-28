"""Twilio integration handler for voice calls via Media Streams WebSocket."""
import os
import json
import base64
import struct
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Twilio Media Streams sends mulaw 8kHz mono audio
TWILIO_SAMPLE_RATE = 8000
TWILIO_ENCODING = "mulaw"  # u-law 8-bit

# ── Mulaw <-> Linear PCM conversion tables ──────────────────────
# These avoid depending on the deprecated audioop module.

_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635

# Precomputed mulaw-to-linear16 lookup (256 entries)
_MULAW_DECODE_TABLE: list = []


def _build_mulaw_decode_table():
    """Build mulaw byte -> signed 16-bit PCM lookup table."""
    table = []
    for byte_val in range(256):
        complement = ~byte_val & 0xFF
        sign = complement & 0x80
        exponent = (complement >> 4) & 0x07
        mantissa = complement & 0x0F
        sample = ((mantissa << 3) + _MULAW_BIAS) << exponent
        sample -= _MULAW_BIAS
        if sign:
            sample = -sample
        table.append(sample)
    return table


_MULAW_DECODE_TABLE = _build_mulaw_decode_table()


def mulaw_decode(mulaw_bytes: bytes) -> bytes:
    """Decode mulaw (u-law) bytes to signed 16-bit linear PCM."""
    samples = [_MULAW_DECODE_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Encode signed 16-bit linear PCM to mulaw (u-law) bytes."""
    n_samples = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes[: n_samples * 2])
    mulaw_out = bytearray(n_samples)
    for i, sample in enumerate(samples):
        sign = 0
        if sample < 0:
            sign = 0x80
            sample = -sample
        if sample > _MULAW_CLIP:
            sample = _MULAW_CLIP
        sample += _MULAW_BIAS

        exponent = 7
        for exp in range(7, 0, -1):
            if sample & (1 << (exp + 3)):
                exponent = exp
                break
        else:
            exponent = 0

        mantissa = (sample >> (exponent + 3)) & 0x0F
        mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        mulaw_out[i] = mulaw_byte
    return bytes(mulaw_out)


def resample_8k_to_16k(audio_8k: bytes) -> bytes:
    """Upsample 16-bit PCM from 8kHz to 16kHz via linear interpolation."""
    if len(audio_8k) < 4:
        return audio_8k
    n = len(audio_8k) // 2
    samples = struct.unpack(f"<{n}h", audio_8k[: n * 2])
    resampled = []
    for i in range(len(samples) - 1):
        resampled.append(samples[i])
        resampled.append((samples[i] + samples[i + 1]) // 2)
    if samples:
        resampled.append(samples[-1])
    return struct.pack(f"<{len(resampled)}h", *resampled)


def resample_16k_to_8k(audio_16k: bytes) -> bytes:
    """Downsample 16-bit PCM from 16kHz to 8kHz (every other sample)."""
    if len(audio_16k) < 4:
        return audio_16k
    n = len(audio_16k) // 2
    samples = struct.unpack(f"<{n}h", audio_16k[: n * 2])
    downsampled = samples[::2]
    return struct.pack(f"<{len(downsampled)}h", *downsampled)


def strip_wav_header(audio_data: bytes) -> bytes:
    """Strip WAV header if present, returning raw PCM."""
    if len(audio_data) < 44 or audio_data[:4] != b"RIFF":
        return audio_data
    pos = 12
    while pos < len(audio_data) - 8:
        chunk_id = audio_data[pos: pos + 4]
        chunk_size = struct.unpack_from("<I", audio_data, pos + 4)[0]
        if chunk_id == b"data":
            return audio_data[pos + 8: pos + 8 + chunk_size]
        pos += 8 + chunk_size
    return audio_data[44:]


@dataclass
class TwilioCallInfo:
    """Information about a Twilio Media Streams call."""
    call_sid: str
    stream_sid: str
    phone_number: str
    account_sid: str = ""
    custom_parameters: Dict[str, str] = field(default_factory=dict)


class TwilioHandler:
    """Handler for Twilio telephony operations."""

    def __init__(
        self,
        account_sid: str = None,
        auth_token: str = None,
        phone_number: str = None,
    ):
        self.account_sid = account_sid or TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or TWILIO_AUTH_TOKEN
        self.phone_number = phone_number or TWILIO_PHONE_NUMBER

    def parse_start_event(self, data: Dict[str, Any]) -> TwilioCallInfo:
        """Parse the 'start' WebSocket event from Twilio Media Streams."""
        start = data.get("start", {})
        custom_params = start.get("customParameters", {})

        phone = custom_params.get("phone", "")
        # Twilio sends numbers in E.164: +91XXXXXXXXXX
        phone = phone.replace("+91", "").replace("+", "").replace(" ", "").strip()
        if len(phone) > 10:
            phone = phone[-10:]

        return TwilioCallInfo(
            call_sid=start.get("callSid", ""),
            stream_sid=start.get("streamSid", ""),
            phone_number=phone,
            account_sid=start.get("accountSid", ""),
            custom_parameters=custom_params,
        )

    @staticmethod
    def decode_audio(payload: str) -> bytes:
        """Decode base64 mulaw audio from Twilio, return 16-bit PCM at 8kHz."""
        mulaw_bytes = base64.b64decode(payload)
        return mulaw_decode(mulaw_bytes)

    @staticmethod
    def encode_audio(pcm_data: bytes) -> str:
        """Encode 16-bit PCM (8kHz) to base64 mulaw for Twilio."""
        mulaw_bytes = pcm16_to_mulaw(pcm_data)
        return base64.b64encode(mulaw_bytes).decode("utf-8")

    @staticmethod
    def create_media_message(stream_sid: str, pcm_audio: bytes) -> dict:
        """Create a media message to send audio back to Twilio.

        Accepts raw 16-bit PCM at 8kHz, encodes to mulaw + base64.
        """
        return {
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": TwilioHandler.encode_audio(pcm_audio),
            },
        }

    @staticmethod
    def create_mark_message(stream_sid: str, name: str) -> dict:
        """Create a mark message for tracking playback."""
        return {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": name},
        }

    @staticmethod
    def create_clear_message(stream_sid: str) -> dict:
        """Create a clear message to interrupt current playback."""
        return {
            "event": "clear",
            "streamSid": stream_sid,
        }

    async def make_outbound_call(
        self,
        to_number: str,
        twiml_url: str,
        status_callback: str = None,
    ) -> Optional[str]:
        """Initiate an outbound call via Twilio REST API."""
        url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.account_sid}/Calls.json"
        )
        data = {
            "To": f"+91{to_number}",
            "From": self.phone_number,
            "Url": twiml_url,
        }
        if status_callback:
            data["StatusCallback"] = status_callback

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data=data,
                    auth=(self.account_sid, self.auth_token),
                    timeout=30.0,
                )
                if response.status_code == 201:
                    result = response.json()
                    call_sid = result.get("sid")
                    logger.info(f"Outbound call initiated: {call_sid}")
                    return call_sid
                else:
                    logger.error(
                        f"Twilio call error: {response.status_code} {response.text}"
                    )
                    return None
        except Exception as e:
            logger.error(f"Error making outbound call: {e}")
            return None

    async def handle_status_callback(
        self, callback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Twilio status callback webhook."""
        call_sid = callback_data.get("CallSid", "")
        status = callback_data.get("CallStatus", "")
        duration = callback_data.get("CallDuration", 0)
        from_number = callback_data.get("From", "")

        logger.info(
            f"Call {call_sid} status: {status}, duration: {duration}s, "
            f"from: {from_number}"
        )

        return {
            "call_sid": call_sid,
            "status": status,
            "duration": duration,
            "from": from_number,
        }