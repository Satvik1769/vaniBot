"""Text correction layer for post-STT processing.

Fixes common STT errors, normalizes Hinglish, and applies domain-specific corrections.
Includes transliteration from Devanagari to Roman script using Google Cloud Translation API.
"""
import os
import re
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# TRANSLITERATION - Devanagari to Roman script
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# POST-TRANSLITERATION CORRECTIONS
# Maps phonetic Hindi spellings of English words back to English
# (When users speak English but STT transcribes in Devanagari)
# ══════════════════════════════════════════════════════════════════════════════

PHONETIC_ENGLISH_CORRECTIONS = {
    # Swap / History related
    'svata': 'swap',
    'svaap': 'swap',
    'svap': 'swap',
    'svaad': 'swap',
    'swaad' : 'swap',
    'svaada':'swap',
    'swaada':'swap',

    'swaap': 'swap',
    'histree': 'history',
    'histaree': 'history',
    'histri': 'history',
    'hishtree': 'history',
    'hishtaree': 'history',

    # DSK related
    'deeesake': 'dsk',
    'deeeske': 'dsk',
    'deesk': 'dsk',
    'deesake': 'dsk',
    'dsk': 'dsk',
    'dee es ke': 'dsk',

    # Station related
    'steshana': 'station',
    'steshan': 'station',
    'steshna': 'station',
    'stesan': 'station',
    'stesana': 'station',

    # Nearest related
    'neresta': 'nearest',
    'neerest': 'nearest',
    'niarest': 'nearest',
    'niyaresta': 'nearest',
    'niyarest': 'nearest',

    # Battery related
    'baitaree': 'battery',
    'baitree': 'battery',
    'baitri': 'battery',
    'betaree': 'battery',
    'betree': 'battery',
    'batree': 'battery',
    'baataree': 'battery',

    # Subscription related
    'sabsakripshana': 'subscription',
    'sabskripshan': 'subscription',
    'subscription': 'subscription',
    'sabsakripsan': 'subscription',

    # Location words
    'lokeshana': 'location',
    'lokeshan': 'location',
    'veyara': 'where',
    'vheyara': 'where',
    'vhaata': 'what',
    'whata': 'what',
    'isa': 'is',
    'da': 'the',
    'phroma': 'from',
    'frama': 'from',
    'araaunda': 'around',
    'araunda': 'around',
    'mee': 'me',

    # Plan related
    'plaina': 'plan',
    'plaana': 'plan',
    'plaan': 'plan',

    # Invoice related
    'invoisa': 'invoice',
    'invois': 'invoice',
    'invoica': 'invoice',

    # Check related
    'cheka': 'check',
    'chek': 'check',

    'riplesamenta':'replacement',
    # Show/Display
    'dikhaao': 'dikhao',
    'dikha': 'dikhao',
    'sho': 'show',
    'shoa': 'show',

    # Common verbs
    'bataa': 'batao',
    'bataao': 'batao',
    'batana': 'batao',
    'bataaen': 'batao',
    'bataen': 'batao',
    'bataiye': 'batao',
    'bataiyee': 'batao',
    'jaananaa': 'jaanna',
    'jaanana': 'jaanna',
    'jaanaa': 'jaana',
    'dikhaaen': 'dikhao',
    'dikhaen': 'dikhao',
    'dikhaiye': 'dikhao',

    # Common words
    'sakate': 'sakte',
    'sakata': 'sakta',
    'sakatee': 'sakti',
    'karanaa': 'karna',
    'karana': 'karna',
    'dekhana': 'dekhna',
    'dekhanaa': 'dekhna',
    'men': 'mein',
    'aapa': 'aap',
    'meree': 'meri',
    'meera': 'mera',
    'meraa': 'mera',
    'kyaa': 'kya',
    'hain?': 'hai?',

    # Leave related
    'leeva': 'leave',
    'leev': 'leave',
    'chhuttee': 'chutti',
    'chuttee': 'chutti',

    # Availability
    'availebilitee': 'availability',
    'availabiliti': 'availability',
    'eveilebal': 'available',
    'eveilebala': 'available',

    # Service
    'sarvisa': 'service',
    'sarvis': 'service',

    # Number related
    'nambara': 'number',
    'nambar': 'number',

    # Status
    'stetasa': 'status',
    'stetas': 'status',

    # Renew
    'rinyu': 'renew',
    'rinyua': 'renew',
    'rinyoo': 'renew',

    # Price/Pricing
    'praisa': 'price',
    'prais': 'price',
    'praisinga': 'pricing',
    'praising': 'pricing',

    # Monthly/Weekly/Daily
    'manthalee': 'monthly',
    'manthlee': 'monthly',
    'weekalee': 'weekly',
    'weeklee': 'weekly',
    'deilee': 'daily',
    'dailee': 'daily',
}

# Devanagari to Roman mapping (ITRANS-like scheme optimized for NLU matching)
DEVANAGARI_TO_ROMAN = {
    # Vowels
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo',
    'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
    # Vowel marks (matras)
    'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
    'ृ': 'ri', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
    # Consonants
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'n',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'n',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh',
    'ष': 'sh', 'स': 's', 'ह': 'h',
    # Special consonants
    'क़': 'q', 'ख़': 'kh', 'ग़': 'g', 'ज़': 'z', 'ड़': 'd',
    'ढ़': 'dh', 'फ़': 'f', 'य़': 'y', 'ऱ': 'r', 'ऴ': 'l',
    # Conjuncts and special characters
    'ं': 'n', 'ः': 'h', 'ँ': 'n',
    '्': '',  # Virama (halant) - suppresses inherent vowel
    # Punctuation
    '।': '.', '॥': '.',
    # Numbers
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
}


class HinglishTransliterator:
    """Transliterates Devanagari text to Roman script for NLU matching.

    Uses a hybrid approach:
    1. Fast local transliteration using character mapping (primary)
    2. Google Cloud Translation API for refinement (optional fallback)

    Handles:
    - Pure Hindi (Devanagari) -> Roman
    - Mixed Hinglish (Devanagari + English) -> Roman
    - Pure English -> Pass through unchanged
    """

    DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')
    DEVANAGARI_WORD = re.compile(r'[\u0900-\u097F]+')

    def __init__(self, use_google_api: bool = True):
        """Initialize transliterator.

        Args:
            use_google_api: If True, use Google Translate API for better results.
                           If False, use only local character mapping.
        """
        self.use_google_api = use_google_api
        self._google_client = None
        self._google_initialized = False

    def _ensure_google_client(self):
        """Lazy initialization of Google Translate client."""
        if not self._google_initialized and self.use_google_api:
            try:
                from google.cloud import translate_v2 as translate
                self._google_client = translate.Client()
                self._google_initialized = True
                logger.info("Google Translate client initialized for transliteration")
            except Exception as e:
                logger.warning(f"Google Translate unavailable, using local transliteration: {e}")
                self._google_initialized = True
                self._google_client = None

    def contains_devanagari(self, text: str) -> bool:
        """Check if text contains Devanagari characters."""
        return bool(self.DEVANAGARI_RANGE.search(text))

    def _local_transliterate(self, text: str) -> str:
        """Transliterate using local character mapping.

        Fast and reliable, doesn't require API calls.
        """
        result = []
        i = 0
        chars = list(text)

        while i < len(chars):
            char = chars[i]

            if char in DEVANAGARI_TO_ROMAN:
                roman = DEVANAGARI_TO_ROMAN[char]

                # Handle consonant + inherent 'a' vowel
                # In Devanagari, consonants have inherent 'a' unless followed by:
                # - A vowel mark (matra)
                # - Virama (्)
                # - End of word
                if roman and char not in 'ािीुूृेैोौंःँ्' and ord(char) >= 0x0915 and ord(char) <= 0x0939:
                    # It's a consonant - check if we need to add inherent 'a'
                    next_char = chars[i + 1] if i + 1 < len(chars) else None

                    # Add the consonant
                    result.append(roman)

                    # Add inherent 'a' if next char is not a matra or virama
                    if next_char:
                        if next_char not in 'ािीुूृेैोौ्ंःँ' and next_char not in DEVANAGARI_TO_ROMAN:
                            # Next is not a modifier, add 'a'
                            result.append('a')
                        elif next_char not in 'ािीुूृेैोौ्':
                            # Next is anusvara/visarga but not matra/virama
                            result.append('a')
                    else:
                        # End of text, add 'a'
                        result.append('a')
                else:
                    result.append(roman)
            else:
                # Not Devanagari, keep as is
                result.append(char)

            i += 1

        return ''.join(result)

    def _clean_transliteration(self, text: str) -> str:
        """Clean up transliterated text for better NLU matching."""
        # Remove double spaces
        text = re.sub(r'\s+', ' ', text)
        # Normalize to lowercase
        text = text.lower().strip()
        return text

    def _apply_phonetic_corrections(self, text: str) -> str:
        """Apply phonetic English corrections to transliterated text.

        Fixes cases where English words were spoken but transcribed
        phonetically in Devanagari, then transliterated back.
        e.g., "स्वत हिस्ट्री" -> "svata histree" -> "swap history"
        """
        words = text.split()
        corrected_words = []

        for word in words:
            # Remove punctuation for matching
            clean_word = word.rstrip('.,?!।')
            punct = word[len(clean_word):] if len(clean_word) < len(word) else ''

            # Check for correction
            if clean_word in PHONETIC_ENGLISH_CORRECTIONS:
                corrected = PHONETIC_ENGLISH_CORRECTIONS[clean_word] + punct
                corrected_words.append(corrected)
            else:
                corrected_words.append(word)

        return ' '.join(corrected_words)

    def transliterate(self, text: str) -> str:
        """Transliterate Devanagari to Roman script.

        Args:
            text: Input text (may contain Devanagari, English, or mixed)

        Returns:
            Romanized text optimized for Hinglish NLU matching.
        """
        if not text or not text.strip():
            return text

        if not self.contains_devanagari(text):
            return text

        # Try Google API first if enabled (better quality)
        if self.use_google_api:
            self._ensure_google_client()
            if self._google_client:
                try:
                    # Google Translate will convert Hindi to English
                    # This gives us a semantic understanding, not just transliteration
                    # But for NLU purposes, we want transliteration
                    # So we use local method as primary
                    pass
                except Exception as e:
                    logger.debug(f"Google API error, using local: {e}")

        # Use local transliteration (fast and reliable)
        result = self._local_transliterate(text)
        result = self._clean_transliteration(result)
        # Apply phonetic corrections for English words transcribed in Hindi
        result = self._apply_phonetic_corrections(result)

        logger.info(f"Transliterated: '{text}' -> '{result}'")
        return result

    async def transliterate_async(self, text: str) -> str:
        """Async transliteration with optional Google API enhancement.

        For voice applications, uses:
        1. Local transliteration (fast, ~0ms)
        2. Optional Google API call for refinement
        """
        if not text or not text.strip():
            return text

        if not self.contains_devanagari(text):
            return text

        # Primary: Local transliteration (instant)
        local_result = self._local_transliterate(text)
        local_result = self._clean_transliteration(local_result)
        # Apply phonetic corrections for English words transcribed in Hindi
        local_result = self._apply_phonetic_corrections(local_result)

        # Optional: Try Google for better results on complex text
        if self.use_google_api and len(text) > 10:
            try:
                google_result = await self._google_transliterate_async(text)
                if google_result and google_result != text:
                    # Google returned something, use it if it looks reasonable
                    # But prefer local for NLU matching since our NLU is trained on Hinglish
                    logger.debug(f"Google result: '{google_result}', Local result: '{local_result}'")
                    # Use local result as it matches our NLU training data better
            except Exception as e:
                logger.debug(f"Google API error: {e}")

        logger.info(f"Transliterated: '{text}' -> '{local_result}'")
        return local_result

    async def _google_transliterate_async(self, text: str) -> Optional[str]:
        """Call Google Translate API asynchronously."""
        try:
            from google.auth import default
            from google.auth.transport.requests import Request

            credentials, project = default()
            credentials.refresh(Request())

            async with httpx.AsyncClient(timeout=3.0) as client:
                # Use romanization endpoint if available (v3 API)
                # Fall back to translation
                response = await client.post(
                    "https://translation.googleapis.com/language/translate/v2",
                    headers={
                        "Authorization": f"Bearer {credentials.token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "q": text,
                        "source": "hi",
                        "target": "en",
                        "format": "text"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["data"]["translations"][0]["translatedText"]

        except Exception as e:
            logger.debug(f"Google transliteration error: {e}")

        return None


# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN VOCABULARY - Battery Smart specific terms
# ══════════════════════════════════════════════════════════════════════════════

# Common STT mistakes → correct term
DOMAIN_CORRECTIONS: Dict[str, str] = {
    # Battery/Station related
    "battery smart": "Battery Smart",
    "betri smart": "Battery Smart",
    "battery start": "Battery Smart",
    "bettery smart": "Battery Smart",
    "batri smart": "Battery Smart",
    "battrey smart": "Battery Smart",

    "swap station": "swap station",
    "swapping station": "swap station",
    "swap stasan": "swap station",
    "swap steshan": "swap station",
    "swop station": "swap station",

    "battery swap": "battery swap",
    "betri swap": "battery swap",
    "battery swop": "battery swap",

    "charging station": "charging station",
    "chargin station": "charging station",
    "charge station": "charging station",

    # Subscription/Plan related
    "subscription": "subscription",
    "subscripsan": "subscription",
    "subscribtion": "subscription",
    "suscription": "subscription",

    "monthly plan": "monthly plan",
    "monthli plan": "monthly plan",

    # Location related
    "nearest station": "nearest station",
    "nerest station": "nearest station",
    "neerest station": "nearest station",
    "near station": "nearest station",

    # Common Hindi/Hinglish
    "kaha hai": "kahan hai",
    "kaha he": "kahan hai",
    "kahan he": "kahan hai",
    "kahaan hai": "kahan hai",

    "batao": "batao",
    "bata do": "batao",
    "batado": "batao",

    "dikha do": "dikhao",
    "dikhado": "dikhao",
    "dikhaao": "dikhao",

    "chahiye": "chahiye",
    "chaiye": "chahiye",
    "chahie": "chahiye",

    "kitna": "kitna",
    "kitni": "kitni",
    "kitnaa": "kitna",

    # Numbers often misheard
    "do": "2",  # Context dependent
    "teen": "3",
    "char": "4",
    "paanch": "5",
    "panch": "5",
    "che": "6",
    "saat": "7",
    "aath": "8",
    "nau": "9",
    "das": "10",
}

# Phonetically similar corrections for Hindi
PHONETIC_CORRECTIONS: Dict[str, str] = {
    # Common phonetic errors in Hindi ASR
    "bhaiya": "bhaiya",
    "bhaya": "bhaiya",
    "bhai": "bhaiya",

    "namaste": "namaste",
    "namasthe": "namaste",
    "namastay": "namaste",

    "dhanyawad": "dhanyawad",
    "dhanyavaad": "dhanyawad",
    "thank you": "dhanyawad",

    "haan": "haan",
    "ha": "haan",
    "han": "haan",

    "nahi": "nahi",
    "nhi": "nahi",
    "nahin": "nahi",

    "theek hai": "theek hai",
    "thik hai": "theek hai",
    "ok": "theek hai",
    "okay": "theek hai",
}

# City names commonly misheard
CITY_CORRECTIONS: Dict[str, str] = {
    "dilli": "Delhi",
    "delhi": "Delhi",
    "new delhi": "Delhi",

    "mumbai": "Mumbai",
    "bombay": "Mumbai",

    "bangalore": "Bangalore",
    "bengaluru": "Bangalore",
    "banglore": "Bangalore",

    "hyderabad": "Hyderabad",
    "hydrabad": "Hyderabad",

    "chennai": "Chennai",
    "madras": "Chennai",

    "kolkata": "Kolkata",
    "calcutta": "Kolkata",

    "pune": "Pune",
    "poona": "Pune",

    "gurgaon": "Gurgaon",
    "gurugram": "Gurgaon",

    "noida": "Noida",
    "greater noida": "Greater Noida",

    "faridabad": "Faridabad",
    "ghaziabad": "Ghaziabad",
}


@dataclass
class CorrectionResult:
    """Result from text correction."""
    original: str
    corrected: str
    corrections_made: List[str]
    confidence_boost: float  # How much to boost confidence after corrections


class TextCorrector:
    """Corrects STT output using domain knowledge and rules."""

    def __init__(self):
        # Compile all corrections into single lookup
        self.corrections = {}
        self.corrections.update(DOMAIN_CORRECTIONS)
        self.corrections.update(PHONETIC_CORRECTIONS)
        self.corrections.update(CITY_CORRECTIONS)

        # Build regex patterns for multi-word corrections
        self._build_patterns()

    def _build_patterns(self):
        """Build regex patterns for corrections."""
        # Sort by length (longest first) to avoid partial matches
        sorted_keys = sorted(self.corrections.keys(), key=len, reverse=True)

        # Create pattern that matches whole words
        self.patterns = []
        for key in sorted_keys:
            pattern = re.compile(r'\b' + re.escape(key) + r'\b', re.IGNORECASE)
            self.patterns.append((pattern, self.corrections[key]))

    def correct(self, text: str) -> CorrectionResult:
        """Apply all corrections to text.

        Returns:
            CorrectionResult with original, corrected text, and details
        """
        if not text or not text.strip():
            return CorrectionResult(
                original=text,
                corrected=text,
                corrections_made=[],
                confidence_boost=0.0
            )

        original = text
        corrected = text
        corrections_made = []

        # Apply pattern-based corrections
        for pattern, replacement in self.patterns:
            if pattern.search(corrected):
                new_text = pattern.sub(replacement, corrected)
                if new_text != corrected:
                    corrections_made.append(f"'{pattern.pattern}' → '{replacement}'")
                    corrected = new_text

        # Normalize whitespace
        corrected = ' '.join(corrected.split())

        # Calculate confidence boost based on corrections
        confidence_boost = min(0.1, len(corrections_made) * 0.02)

        return CorrectionResult(
            original=original,
            corrected=corrected,
            corrections_made=corrections_made,
            confidence_boost=confidence_boost
        )

    def normalize_hinglish(self, text: str) -> str:
        """Normalize Hinglish text for better intent matching.

        Standardizes common variations in Romanized Hindi.
        """
        if not text:
            return text

        # Common normalizations
        normalizations = [
            # Question words
            (r'\bkya\b', 'kya'),
            (r'\bkyaa\b', 'kya'),
            (r'\bkaise\b', 'kaise'),
            (r'\bkese\b', 'kaise'),
            (r'\bkahan\b', 'kahan'),
            (r'\bkahaan\b', 'kahan'),
            (r'\bkab\b', 'kab'),
            (r'\bkaun\b', 'kaun'),
            (r'\bkon\b', 'kaun'),

            # Common verbs
            (r'\bhai\b', 'hai'),
            (r'\bhe\b', 'hai'),
            (r'\bhain\b', 'hain'),
            (r'\bhein\b', 'hain'),
            (r'\btha\b', 'tha'),
            (r'\bthi\b', 'thi'),

            # Pronouns
            (r'\bmain\b', 'main'),
            (r'\bmein\b', 'main'),
            (r'\baap\b', 'aap'),
            (r'\btum\b', 'tum'),

            # Common words
            (r'\bachha\b', 'achha'),
            (r'\bachcha\b', 'achha'),
            (r'\baccha\b', 'achha'),
            (r'\bbahut\b', 'bahut'),
            (r'\bbohot\b', 'bahut'),
            (r'\bbohat\b', 'bahut'),
        ]

        result = text.lower()
        for pattern, replacement in normalizations:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        return result


class LLMTextCorrector:
    """Uses LLM for advanced text correction."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.enabled = bool(self.api_key)

        if not self.enabled:
            logger.warning("LLM correction disabled - no OPENAI_API_KEY set")

    async def correct(self, text: str, context: str = "voice assistant for battery swap stations") -> str:
        """Use LLM to correct and normalize text.

        Args:
            text: Raw STT output
            context: Domain context for better corrections

        Returns:
            Corrected text
        """
        if not self.enabled or not text.strip():
            return text

        prompt = f"""Correct this speech-to-text output for a {context}.
Fix spelling errors, normalize Hinglish (Hindi-English mix), but preserve the meaning.
Do NOT add or remove information. Only fix obvious errors.

Input: "{text}"

Output only the corrected text, nothing else."""

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 150
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    corrected = result["choices"][0]["message"]["content"].strip()
                    # Remove quotes if LLM added them
                    corrected = corrected.strip('"\'')
                    logger.debug(f"LLM correction: '{text}' → '{corrected}'")
                    return corrected
                else:
                    logger.warning(f"LLM correction failed: {response.status_code}")
                    return text

        except Exception as e:
            logger.warning(f"LLM correction error: {e}")
            return text


class CorrectionPipeline:
    """Full correction pipeline: transliteration + rules + optional LLM."""

    def __init__(self, use_llm: bool = False, use_transliteration: bool = True):
        self.transliterator = HinglishTransliterator() if use_transliteration else None
        self.rule_corrector = TextCorrector()
        self.llm_corrector = LLMTextCorrector() if use_llm else None

    async def correct(self, text: str) -> CorrectionResult:
        """Run full correction pipeline.

        1. Transliterate Devanagari to Roman (if present)
        2. Apply rule-based corrections (fast, reliable)
        3. Optionally apply LLM correction (slower, more flexible)
        """
        original_text = text
        corrections_made = []

        # Step 1: Transliteration (Devanagari -> Roman)
        if self.transliterator and self.transliterator.contains_devanagari(text):
            transliterated = await self.transliterator.transliterate_async(text)
            if transliterated != text:
                corrections_made.append(f"Transliterated: '{text}' → '{transliterated}'")
                text = transliterated

        # Step 2: Rule-based correction
        result = self.rule_corrector.correct(text)
        corrections_made.extend(result.corrections_made)

        # Step 3: LLM correction (optional)
        if self.llm_corrector and self.llm_corrector.enabled:
            llm_corrected = await self.llm_corrector.correct(result.corrected)
            if llm_corrected != result.corrected:
                corrections_made.append(f"LLM: '{result.corrected}' → '{llm_corrected}'")
                result.corrected = llm_corrected
                result.confidence_boost += 0.05

        return CorrectionResult(
            original=original_text,
            corrected=result.corrected,
            corrections_made=corrections_made,
            confidence_boost=result.confidence_boost
        )

    def correct_sync(self, text: str) -> CorrectionResult:
        """Synchronous rule-based correction only (no transliteration)."""
        return self.rule_corrector.correct(text)

    async def transliterate_only(self, text: str) -> str:
        """Just transliterate without other corrections."""
        if self.transliterator and self.transliterator.contains_devanagari(text):
            return await self.transliterator.transliterate_async(text)
        return text