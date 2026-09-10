# Nomba1BOT

Live-market strategy signal dashboard built around the user's 500-strategy catalog.

## Current build

- 500 selectable strategy definitions from the project specification
- 5m / 15m / 30m analysis model
- Strategy selection with BUY / SELL / NEUTRAL / UNCERTAIN states
- Signal aggregation and confidence scoring
- Live dashboard UI
- Provider-agnostic market-data API contract
- WhatsApp notification adapter interface
- No automatic real-money order execution in this first build

## Architecture

`web/` contains the browser dashboard.

`server/` contains the signal engine and market-data integration points.

The engine deliberately separates **signal calculation** from **execution**. This lets additional strategies and data providers be added without changing the dashboard.

## Run locally

### Frontend
Open `web/index.html` in a browser or serve the `web` directory with any static server.

### Backend
Requires Python 3.11+.

```bash
cd server
pip install -r requirements.txt
python app.py
```

The API starts on `http://localhost:8000`.

## Data providers

Set a supported market-data provider in the server environment before treating the dashboard as live. The UI will clearly show when it is using demo data.

## Notifications

WhatsApp delivery is represented by a provider adapter. Credentials must be stored as server-side secrets, never in browser JavaScript.

## Important

Trading signals are analytical outputs, not guaranteed profitable trades. The system must be tested with historical and paper data before any real-money execution is considered.
