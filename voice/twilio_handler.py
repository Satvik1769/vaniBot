"""Twilio integration handler for voice calls via Media Streams WebSocket."""
import os
import json
import base64
import struct
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import httpx
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d

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
    """Upsample 16-bit PCM from 8kHz to 16kHz using proper DSP.

    Uses polyphase filtering for high-quality upsampling that preserves
    audio fidelity - critical for accurate speech recognition.
    """
    if len(audio_8k) < 4:
        return audio_8k
    n = len(audio_8k) // 2
    samples = np.array(struct.unpack(f"<{n}h", audio_8k[:n * 2]), dtype=np.float32)

    # Polyphase resampling with anti-aliasing
    resampled = signal.resample_poly(samples, up=2, down=1)

    # Clip and convert back
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
    return resampled.tobytes()


def resample_16k_to_8k(audio_16k: bytes) -> bytes:
    """Downsample 16-bit PCM from 16kHz to 8kHz using proper DSP.

    Uses polyphase filtering with anti-aliasing to prevent artifacts.
    """
    if len(audio_16k) < 4:
        return audio_16k
    n = len(audio_16k) // 2
    samples = np.array(struct.unpack(f"<{n}h", audio_16k[:n * 2]), dtype=np.float32)

    # Polyphase downsampling with anti-aliasing
    downsampled = signal.resample_poly(samples, up=1, down=2)

    # Clip and convert back
    downsampled = np.clip(downsampled, -32768, 32767).astype(np.int16)
    return downsampled.tobytes()


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO PREPROCESSING UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def bytes_to_samples(audio_data: bytes) -> np.ndarray:
    """Convert PCM bytes to numpy float array."""
    n = len(audio_data) // 2
    if n == 0:
        return np.array([], dtype=np.float32)
    samples = np.array(struct.unpack(f"<{n}h", audio_data[:n * 2]), dtype=np.float32)
    return samples


def samples_to_bytes(samples: np.ndarray) -> bytes:
    """Convert numpy array back to PCM bytes."""
    clipped = np.clip(samples, -32768, 32767).astype(np.int16)
    return clipped.tobytes()


def calculate_rms(audio_data: bytes) -> float:
    """Calculate RMS energy level of audio."""
    samples = bytes_to_samples(audio_data)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples ** 2)))


def calculate_rms_db(audio_data: bytes) -> float:
    """Calculate RMS in decibels (relative to full scale)."""
    rms = calculate_rms(audio_data)
    if rms < 1:
        return -96.0  # Essentially silence
    return 20 * np.log10(rms / 32768)


def has_speech(audio_data: bytes, threshold_db: float = -35.0) -> bool:
    """Detect if audio chunk contains speech using energy threshold.

    Args:
        audio_data: Raw 16-bit PCM bytes
        threshold_db: dB threshold (-35 to -25 typical for telephony)

    Returns:
        True if likely speech, False if silence/noise
    """
    rms_db = calculate_rms_db(audio_data)
    return rms_db > threshold_db


def estimate_noise_floor(audio_chunks: list[bytes], percentile: int = 10) -> float:
    """Estimate noise floor from audio chunks.

    Uses lowest percentile of RMS values as noise estimate.
    """
    if not audio_chunks:
        return 0.0
    rms_values = [calculate_rms(chunk) for chunk in audio_chunks]
    return float(np.percentile(rms_values, percentile))


def normalize_audio(audio_data: bytes, target_db: float = -3.0) -> bytes:
    """Normalize audio to target dB level.

    Args:
        audio_data: Raw 16-bit PCM bytes
        target_db: Target dB level relative to full scale

    Returns:
        Normalized audio bytes
    """
    samples = bytes_to_samples(audio_data)
    if len(samples) == 0:
        return audio_data

    rms = np.sqrt(np.mean(samples ** 2))
    if rms < 1:
        return audio_data  # Too quiet, likely silence

    # Calculate gain
    target_rms = 32768 * (10 ** (target_db / 20))
    gain = target_rms / rms

    # Limit gain to prevent over-amplification
    gain = min(gain, 8.0)

    normalized = samples * gain
    return samples_to_bytes(normalized)


def remove_dc_offset(audio_data: bytes) -> bytes:
    """Remove DC offset from audio signal."""
    samples = bytes_to_samples(audio_data)
    if len(samples) == 0:
        return audio_data

    # Subtract mean (DC component)
    samples = samples - np.mean(samples)
    return samples_to_bytes(samples)


def apply_highpass_filter(audio_data: bytes, cutoff_hz: float = 80.0,
                          sample_rate: int = 8000) -> bytes:
    """Apply high-pass filter to remove low-frequency noise.

    Removes rumble, DC offset, and low-frequency interference.
    """
    samples = bytes_to_samples(audio_data)
    if len(samples) < 10:
        return audio_data

    # Design Butterworth high-pass filter
    nyquist = sample_rate / 2
    normalized_cutoff = cutoff_hz / nyquist
    b, a = signal.butter(2, normalized_cutoff, btype='high')

    # Apply filter
    filtered = signal.filtfilt(b, a, samples)
    return samples_to_bytes(filtered)


def apply_lowpass_filter(audio_data: bytes, cutoff_hz: float = 3400.0,
                         sample_rate: int = 8000) -> bytes:
    """Apply low-pass filter (telephony bandwidth limit).

    Telephony is typically 300-3400 Hz.
    """
    samples = bytes_to_samples(audio_data)
    if len(samples) < 10:
        return audio_data

    nyquist = sample_rate / 2
    normalized_cutoff = min(cutoff_hz / nyquist, 0.99)
    b, a = signal.butter(4, normalized_cutoff, btype='low')

    filtered = signal.filtfilt(b, a, samples)
    return samples_to_bytes(filtered)


def apply_bandpass_filter(audio_data: bytes, low_hz: float = 100.0,
                          high_hz: float = 3400.0, sample_rate: int = 8000) -> bytes:
    """Apply band-pass filter for telephony speech range."""
    samples = bytes_to_samples(audio_data)
    if len(samples) < 10:
        return audio_data

    nyquist = sample_rate / 2
    low = low_hz / nyquist
    high = min(high_hz / nyquist, 0.99)
    b, a = signal.butter(2, [low, high], btype='band')

    filtered = signal.filtfilt(b, a, samples)
    return samples_to_bytes(filtered)


def simple_noise_reduction(audio_data: bytes, noise_floor: float = 200.0,
                           smoothing: int = 3) -> bytes:
    """Simple spectral subtraction noise reduction.

    Args:
        audio_data: Raw PCM bytes
        noise_floor: Estimated noise RMS level
        smoothing: Smoothing window size
    """
    samples = bytes_to_samples(audio_data)
    if len(samples) < 64:
        return audio_data

    # Simple approach: soft threshold based on noise floor
    # Reduce samples below noise floor, preserve those above
    magnitude = np.abs(samples)

    # Smooth magnitude estimate
    smoothed_mag = uniform_filter1d(magnitude.astype(np.float64), size=smoothing)

    # Create gain mask (soft threshold)
    gain = np.clip((smoothed_mag - noise_floor) / (smoothed_mag + 1), 0.1, 1.0)

    # Apply gain
    processed = samples * gain
    return samples_to_bytes(processed)


def trim_silence(audio_data: bytes, threshold_db: float = -40.0,
                 min_silence_ms: int = 100, sample_rate: int = 8000) -> bytes:
    """Trim leading and trailing silence from audio.

    Args:
        audio_data: Raw PCM bytes
        threshold_db: Silence threshold in dB
        min_silence_ms: Minimum silence duration to trim
        sample_rate: Audio sample rate
    """
    samples = bytes_to_samples(audio_data)
    if len(samples) == 0:
        return audio_data

    # Calculate frame-wise energy
    frame_size = int(sample_rate * 0.020)  # 20ms frames
    threshold_linear = 32768 * (10 ** (threshold_db / 20))

    # Find first non-silent frame
    start_idx = 0
    for i in range(0, len(samples) - frame_size, frame_size):
        frame = samples[i:i + frame_size]
        if np.sqrt(np.mean(frame ** 2)) > threshold_linear:
            start_idx = max(0, i - frame_size)  # Keep one frame before
            break

    # Find last non-silent frame
    end_idx = len(samples)
    for i in range(len(samples) - frame_size, 0, -frame_size):
        frame = samples[i:i + frame_size]
        if np.sqrt(np.mean(frame ** 2)) > threshold_linear:
            end_idx = min(len(samples), i + frame_size * 2)  # Keep one frame after
            break

    if start_idx >= end_idx:
        return audio_data  # Don't trim to nothing

    return samples_to_bytes(samples[start_idx:end_idx])


def preprocess_audio_for_stt(audio_data: bytes, sample_rate: int = 8000,
                             noise_floor: float = None) -> bytes:
    """Full preprocessing pipeline for STT.

    Applies: DC removal → highpass → noise reduction → normalization
    """
    if len(audio_data) < 100:
        return audio_data

    # Step 1: Remove DC offset
    audio = remove_dc_offset(audio_data)

    # Step 2: Band-pass filter (telephony range)
    audio = apply_bandpass_filter(audio, low_hz=100, high_hz=3400, sample_rate=sample_rate)

    # Step 3: Simple noise reduction if noise floor provided
    if noise_floor and noise_floor > 50:
        audio = simple_noise_reduction(audio, noise_floor=noise_floor)

    # Step 4: Normalize
    audio = normalize_audio(audio, target_db=-6.0)

    return audio


class VADState:
    """Voice Activity Detection state tracker."""

    def __init__(self,
                 speech_threshold_db: float = -30.0,
                 silence_threshold_db: float = -40.0,
                 speech_min_ms: int = 100,
                 silence_trigger_ms: int = 500,
                 max_speech_ms: int = 10000):
        """
        Args:
            speech_threshold_db: dB level to detect speech start
            silence_threshold_db: dB level to detect silence
            speech_min_ms: Minimum speech duration before considering valid
            silence_trigger_ms: Silence duration to trigger end of utterance
            max_speech_ms: Maximum speech before forced segmentation
        """
        self.speech_threshold_db = speech_threshold_db
        self.silence_threshold_db = silence_threshold_db
        self.speech_min_ms = speech_min_ms
        self.silence_trigger_ms = silence_trigger_ms
        self.max_speech_ms = max_speech_ms

        # State
        self.is_speaking = False
        self.speech_start_ms = 0
        self.silence_start_ms = 0
        self.total_speech_ms = 0
        self.noise_floor_samples: list[float] = []
        self.noise_floor: float = 200.0

    def update_noise_floor(self, rms: float):
        """Update noise floor estimate during silence."""
        self.noise_floor_samples.append(rms)
        if len(self.noise_floor_samples) > 50:
            self.noise_floor_samples.pop(0)
        if len(self.noise_floor_samples) >= 5:
            self.noise_floor = float(np.percentile(self.noise_floor_samples, 20))

    def process_chunk(self, audio_chunk: bytes, chunk_duration_ms: int = 20
                     ) -> Tuple[bool, bool]:
        """Process audio chunk and return VAD state.

        Returns:
            (is_speech, should_finalize):
                - is_speech: True if this chunk is speech
                - should_finalize: True if utterance should be sent to STT
        """
        rms_db = calculate_rms_db(audio_chunk)
        rms = calculate_rms(audio_chunk)

        is_speech = rms_db > self.speech_threshold_db
        is_silence = rms_db < self.silence_threshold_db
        should_finalize = False

        if is_speech:
            if not self.is_speaking:
                # Speech started
                self.is_speaking = True
                self.speech_start_ms = 0
                self.silence_start_ms = 0

            self.speech_start_ms += chunk_duration_ms
            self.total_speech_ms += chunk_duration_ms
            self.silence_start_ms = 0

        elif self.is_speaking:
            # Was speaking, now possibly silence
            self.silence_start_ms += chunk_duration_ms

            # Check if silence long enough to end utterance
            if self.silence_start_ms >= self.silence_trigger_ms:
                if self.total_speech_ms >= self.speech_min_ms:
                    should_finalize = True
                self.is_speaking = False
                self.total_speech_ms = 0
                self.silence_start_ms = 0
        else:
            # Pure silence - update noise floor
            self.update_noise_floor(rms)

        # Force finalize if max speech exceeded
        if self.total_speech_ms >= self.max_speech_ms:
            should_finalize = True
            self.is_speaking = False
            self.total_speech_ms = 0

        return is_speech, should_finalize

    def reset(self):
        """Reset VAD state."""
        self.is_speaking = False
        self.speech_start_ms = 0
        self.silence_start_ms = 0
        self.total_speech_ms = 0


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