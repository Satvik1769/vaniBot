# Battery Smart Voicebot

A voice-enabled conversational AI for Tier-1 driver support, built with Rasa Pro, FastAPI, and real-time voice integration via Twilio.

## What's Included

This voicebot provides:
- **Voice Integration**: Real-time voice calls via Twilio Media Streams with bidirectional audio
- **Speech Processing**: Google Cloud Speech-to-Text for Hindi/Hinglish, Deepgram for TTS
- **Conversational AI**: Rasa Pro with LLM-powered intent classification and response generation
- **Driver Support**: Swap history, station finder, subscription management, DSK/leave requests
- **Multi-language**: Supports Hindi (hi), English (en), and Hinglish (hi-en)

---

## Tools & Technologies

### Core Framework
| Tool | Version | Purpose |
|------|---------|---------|
| Rasa Pro | 3.15.7 | Conversational AI framework with CALM (LLM-native dialogue) |
| Rasa SDK | 3.15.0 | Custom action server |
| FastAPI | 0.109.0 | REST API and WebSocket server |
| Uvicorn | 0.27.0 | ASGI server |

### Voice & Speech
| Tool | Purpose |
|------|---------|
| Twilio Media Streams | Real-time bidirectional voice calls via WebSocket |
| Google Cloud Speech-to-Text | Primary STT for Hindi/Hinglish transcription |
| Google Cloud Text-to-Speech | Fallback TTS |
| Google Cloud Translate | Language translation |
| Deepgram SDK 3.7.0 | STT streaming and TTS synthesis |

### LLM & NLP
| Tool | Purpose |
|------|---------|
| OpenAI GPT-4o | Intent classification, response generation, fallback handling |
| OpenAI Embeddings (text-embedding-3-large) | Vector search for enterprise knowledge base |
| Google Gemini | Alternative LLM provider (configured but optional) |

### Database
| Tool | Purpose |
|------|---------|
| PostgreSQL | Primary database |
| SQLAlchemy 2.0 (async) | ORM with async support |
| asyncpg | Async PostgreSQL driver |
| Alembic | Database migrations |

### Audio Processing
| Tool | Purpose |
|------|---------|
| NumPy | Audio signal processing |
| SciPy | DSP filters, resampling, VAD preprocessing |

### Utilities
| Tool | Purpose |
|------|---------|
| httpx | Async HTTP client for Rasa communication |
| Pydantic | Request/response validation |
| python-dotenv | Environment variable management |
| structlog | Structured logging |
| pytest + pytest-asyncio | Testing framework |

---

## Directory Structure

```
vaniBot/
├── actions/                 # Rasa custom actions (Python)
│   ├── action_swap_history.py      # Fetch driver's battery swap history
│   ├── action_station_finder.py    # Find nearest swap stations
│   ├── action_subscription.py      # Check/manage subscription plans
│   ├── action_dsk_leave.py         # DSK service centers & leave requests
│   ├── action_sentiment.py         # Sentiment analysis during calls
│   ├── action_human_handoff.py     # Transfer to human agent
│   └── action_session.py           # Session management
│
├── api/                     # FastAPI backend
│   ├── main.py                     # App entry point, Twilio webhooks, WebSocket
│   ├── core/
│   │   ├── config.py               # Settings & environment config
│   │   └── database.py             # Async database connection pool
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── driver.py               # Driver entity
│   │   ├── station.py              # Swap station entity
│   │   ├── subscription.py         # Subscription plans
│   │   ├── swap.py                 # Battery swap records
│   │   ├── dsk.py                  # DSK service centers
│   │   └── conversation.py         # Call/conversation logs
│   ├── services/                   # Business logic layer
│   │   ├── driver_service.py       # Driver lookup & validation
│   │   ├── station_service.py      # Station search & availability
│   │   ├── subscription_service.py # Plan management
│   │   ├── swap_service.py         # Swap history queries
│   │   └── dsk_service.py          # DSK/leave operations
│   └── routers/                    # API route handlers
│       ├── drivers.py              # /api/v1/drivers/*
│       ├── stations.py             # /api/v1/stations/*
│       ├── subscriptions.py        # /api/v1/subscriptions/*
│       ├── swaps.py                # /api/v1/swaps/*
│       └── dsk.py                  # /api/v1/dsk/*
│
├── voice/                   # Voice integration layer
│   ├── orchestrator.py             # Main voice session controller
│   ├── twilio_handler.py           # Twilio Media Streams + mulaw codec
│   ├── deepgram_client.py          # Deepgram STT/TTS client
│   ├── text_correction.py          # Post-STT text cleanup & transliteration
│   ├── amazon_connect_handler.py   # Amazon Connect integration (optional)
│   └── exotel_handler.py           # Exotel integration (optional)
│
├── data/                    # Rasa training data
│   ├── general/                    # General conversation flows
│   │   ├── hello.yml               # Greeting flows
│   │   ├── goodbye.yml             # Farewell flows
│   │   ├── help.yml                # Help request flows
│   │   ├── feedback.yml            # Feedback collection
│   │   ├── human_handoff.yml       # Agent transfer flows
│   │   └── show_faqs.yml           # FAQ responses
│   ├── tier1/                      # Tier-1 support flows (business logic)
│   └── system/patterns/            # System patterns (session, fallback, etc.)
│
├── domain/                  # Rasa domain configuration
│   ├── general/                    # General intents, responses, actions
│   ├── tier1/                      # Tier-1 specific domain
│   │   ├── actions.yml             # Custom action declarations
│   │   ├── slots.yml               # Slot definitions
│   │   └── responses.yml           # Bot response templates
│   └── system/patterns/            # System pattern definitions
│
├── db/                      # Database setup
│   ├── schema.sql                  # PostgreSQL schema definition
│   └── seed_data.sql               # Sample data for development
│
├── docs/                    # Knowledge base for RAG
│   └── template.txt                # Enterprise search documents
│
├── prompts/                 # LLM prompt templates
│   └── rephraser_demo_personality_prompt.jinja2  # Response rephrasing prompt
│
├── tests/                   # Test suite
│   └── e2e_test_cases/             # End-to-end conversation tests
│
├── models/                  # Trained Rasa models (generated)
│
├── config.yml               # Rasa pipeline configuration
├── endpoints.yml            # Rasa endpoints & model groups
├── credentials.yml          # Channel credentials
└── requirements.txt         # Python dependencies
```

---

## Getting Started

### Prerequisites

1. Python 3.11+
2. PostgreSQL database
3. API keys for:
   - OpenAI (GPT-4o and embeddings)
   - Deepgram (STT/TTS)
   - Google Cloud (Speech-to-Text, Text-to-Speech)
   - Twilio (for voice calls)

### Environment Setup

Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
# Edit .env with your API keys
```

### Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Services

```bash
# 1. Train Rasa model
rasa train

# 2. Start Rasa server (Terminal 1)
rasa run --enable-api --cors "*"

# 3. Start Actions server (Terminal 2)
rasa run actions

# 4. Start FastAPI server (Terminal 3)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Expose for Twilio webhooks (Terminal 4)
ngrok http 8000
```

### Quick Testing

- **CLI Chat**: `rasa shell` (text-based testing)
- **API Docs**: http://localhost:8000/docs (FastAPI Swagger UI)
- **Rasa API**: http://localhost:5005

### Port Summary

| Service | Port | Description |
|---------|------|-------------|
| Rasa Server | 5005 | Rasa REST API and webhooks |
| Actions Server | 5055 | Custom action execution |
| FastAPI | 8000 | Voice API, Twilio webhooks, business endpoints |

---

## API Endpoints

### Voice Endpoints
- `POST /api/v1/twilio/voice` - Twilio webhook (returns TwiML)
- `WS /ws/twilio-stream` - Twilio Media Streams WebSocket
- `POST /api/v1/voice/outbound-call` - Initiate outbound call

### Business Endpoints
- `GET /api/v1/drivers/{phone}` - Get driver info
- `GET /api/v1/swaps/{driver_id}` - Get swap history
- `GET /api/v1/stations/nearby` - Find nearby stations
- `GET /api/v1/subscriptions/{driver_id}` - Get subscription status
- `GET /api/v1/dsk/centers` - List DSK service centers

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Twilio (Phone Call)                         │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI (api/main.py)                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ TwiML Webhook   │  │ WebSocket       │  │ REST API Routers    │  │
│  │ /twilio/voice   │  │ /ws/twilio-     │  │ /swaps, /stations   │  │
│  └────────┬────────┘  │  stream         │  └─────────────────────┘  │
│           │           └────────┬────────┘                           │
└───────────│────────────────────│────────────────────────────────────┘
            │                    │
            │                    ▼
            │    ┌───────────────────────────────────┐
            │    │    Voice Orchestrator             │
            │    │    (voice/orchestrator.py)        │
            │    │  ┌───────────┐ ┌───────────────┐  │
            │    │  │ Google    │ │ Deepgram      │  │
            │    │  │ STT       │ │ TTS           │  │
            │    │  └─────┬─────┘ └───────┬───────┘  │
            │    └────────│───────────────│──────────┘
            │             │               │
            │             ▼               │
            │    ┌───────────────────┐    │
            │    │ Text Correction   │    │
            │    │ (transliteration) │    │
            │    └─────────┬─────────┘    │
            │              │              │
            └──────────────┼──────────────┘
                           ▼
            ┌───────────────────────────────────────┐
            │            Rasa Pro                   │
            │  ┌─────────────┐ ┌─────────────────┐  │
            │  │ CALM/LLM    │ │ Enterprise      │  │
            │  │ Dialogue    │ │ Search (FAISS)  │  │
            │  └──────┬──────┘ └─────────────────┘  │
            └─────────│─────────────────────────────┘
                      │
                      ▼
            ┌───────────────────────────────────────┐
            │         Actions Server                │
            │  (actions/*.py)                       │
            │  Swap History, Station Finder, etc.   │
            └─────────────────┬─────────────────────┘
                              │
                              ▼
            ┌───────────────────────────────────────┐
            │           PostgreSQL                  │
            │  Drivers, Swaps, Stations, Plans      │
            └───────────────────────────────────────┘
```