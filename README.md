# Basic Rasa Template

A simple, general-purpose conversational agent template that provides essential conversational capabilities.

## 🚀 What's Included

This template provides a foundation for building conversational agents with:
- **Basic conversational flows**: Greetings, help, feedback, and human handoff
- **Help system**: Users can ask for assistance and get guided responses
- **Feedback collection**: Gather user feedback to improve the agent
- **Human handoff**: Seamlessly transfer conversations to human agents when needed

## 📁 Directory Structure

```
├── actions/          # Custom Python logic for agent actions
├── data/            # Conversational flows and training data
├── domain/          # Agent configuration (slots, responses, actions)
├── docs/            # Knowledge base documents (optional)
├── prompts/         # LLM prompts for enhanced responses
└── config.yml       # Training pipeline configuration
```

## Starting Project

-  rasa train                                                                                                                                                                                               
-   rasa run --enable-api --cors "*"                                                                                                                                                                         
  This runs on port 5005 by default.   
-  rasa run actions                                                                                                                                                                                         
  This runs on port 5055 by default. 
-  python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload  
- ngrok http 8000


```
  Quick Testing                                                                                                                                                                                            
                                                                                                                                                                                                           
  - Chat via CLI: rasa shell (for text-based testing)                                                                                                                                                      
  - API endpoint: http://localhost:8000 (FastAPI docs at /docs)                                                                                                                                            
  - Rasa API: http://localhost:5005   
  
```


```

  Summary of Ports                                                                                                                                                                                         
  ┌─────────────────────┬──────┐                                                                                                                                                                           
  │       Service       │ Port │                                                                                                                                                                           
  ├─────────────────────┼──────┤                                                                                                                                                                           
  │ Rasa Server         │ 5005 │                                                                                                                                                                           
  ├─────────────────────┼──────┤                                                                                                                                                                           
  │ Actions Server      │ 5055 │                                                                                                                                                                           
  ├─────────────────────┼──────┤                                                                                                                                                                           
  │ FastAPI (Voice/API) │ 8000 │                                                                                                                                                                           
  └─────────────────────┴──────┘                                                                                                                                                                           
```