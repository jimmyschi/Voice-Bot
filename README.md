# Voice-Bot

An automated voice bot that calls the Athena AI agent, simulates realistic patient scenarios, records and transcribes every conversation, and generates a bug report from the findings.

## Requirements

- Python 3.11+
- A [Twilio](https://www.twilio.com/) account with a phone number
- A [Deepgram](https://deepgram.com/) API key
- An [Anthropic](https://www.anthropic.com/) API key
- An [ngrok](https://ngrok.com/) account (free tier is fine) — only needed if you don't have a public server

## Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/jimmyschi/Voice-Bot.git
cd Voice-Bot

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and fill in your API keys (see comments in the file)

# 5. Authenticate ngrok (one-time)
ngrok config add-authtoken <your_ngrok_authtoken>
```

## Running

### Run all 17 scenarios (recommended)

```bash
python main.py run
```

This dials the Athena test number for each scenario, waits for each call to finish, then generates a bug report in `bug_reports/bug_report.md`.

### Run a single scenario

```bash
# See all available scenario IDs
python main.py list

# Run one scenario
python main.py single --scenario weekend_appointment
```

### Analyze transcripts only (without making new calls)

```bash
python main.py analyze
```

## Output

| Directory | Contents |
|-----------|----------|
| `transcripts/` | `<call_sid>.json` (machine-readable) and `<call_sid>.txt` (human-readable) for every call |
| `recordings/` | `<call_sid>.mp3` — Twilio dual-channel recording of both sides |
| `bug_reports/` | `bug_report.md` — structured list of all issues found |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID (starts with AC) |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Your Twilio phone number in E.164 format |
| `DEEPGRAM_API_KEY` | Deepgram API key (used for both STT and TTS) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `WEBHOOK_URL` | (Optional) Public HTTPS base URL if you deploy to a server instead of ngrok |
| `TARGET_NUMBER` | Target number to call (defaults to `+18054398008`) |
