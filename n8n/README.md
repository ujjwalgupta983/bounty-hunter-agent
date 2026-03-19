# n8n Workflow Automations

This directory contains [n8n](https://n8n.io) workflow JSON files that complement the Bounty Hunter Agent with automated notifications and tracking.

## Workflows

| File | Trigger | Description |
|---|---|---|
| `daily-digest.json` | Daily at 9am | Fetches dashboard stats + top 5 bounties, sends Telegram digest |
| `pr-merged-payout-tracker.json` | Webhook POST `/webhook/pr-merged` | Records earnings when a PR is merged, sends Telegram notification |
| `high-value-alert.json` | Every hour | Alerts via Telegram when any bounty > $500 is detected |

## Prerequisites

- Docker + Docker Compose
- The bounty-hunter-agent Docker network must exist (`bounty-hunter-agent_default`)
- A Telegram Bot token and chat ID (see [Telegram Bot setup](#telegram-bot-setup))

## Quick Start

### 1. Start n8n

```bash
# From the repo root
docker compose -f n8n/docker-compose.yml up -d
```

n8n will be available at [http://localhost:5678](http://localhost:5678).

### 2. Import Workflows

Use the n8n CLI inside the container — this is the most reliable method:

```bash
docker exec n8n-n8n-1 n8n import:workflow --input=/workflows/daily-digest.json
docker exec n8n-n8n-1 n8n import:workflow --input=/workflows/pr-merged-payout-tracker.json
docker exec n8n-n8n-1 n8n import:workflow --input=/workflows/high-value-alert.json
```

Verify the imports:

```bash
docker exec n8n-n8n-1 n8n list:workflow
```

Alternatively you can import via the UI: open [http://localhost:5678](http://localhost:5678), go to **Workflows → Import from File**, and select each JSON from `n8n/workflows/`.

### 3. Configure Telegram Credentials

1. In n8n, go to **Credentials → New Credential → Telegram**
2. Enter your **Bot Token** (from [@BotFather](https://t.me/BotFather))
3. Name it exactly `Telegram Bot` (to match the credential name in the workflow JSONs)
4. Save

### 4. Set Environment Variables

Create or update `config/.env` with:

```env
# n8n
N8N_ENCRYPTION_KEY=your-random-secret-key-here
TELEGRAM_CHAT_ID=your-telegram-chat-id
```

To get your `TELEGRAM_CHAT_ID`, message [@userinfobot](https://t.me/userinfobot) on Telegram.

### 5. Activate Workflows

In the n8n UI, open each imported workflow and toggle it to **Active**.

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token BotFather gives you
4. Start a chat with your new bot
5. Get your chat ID from [@userinfobot](https://t.me/userinfobot)

## Webhook: PR Merged Payout Tracker

The `pr-merged-payout-tracker` workflow exposes a webhook endpoint:

```
POST http://localhost:5678/webhook/pr-merged
```

Expected payload:

```json
{
  "repository": {"full_name": "owner/repo"},
  "pull_request": {
    "number": 42,
    "merged_at": "2026-03-19T10:00:00Z"
  },
  "bounty_amount_usd": 250
}
```

You can trigger this manually for testing:

```bash
curl -X POST http://localhost:5678/webhook/pr-merged \
  -H "Content-Type: application/json" \
  -d '{"repository": {"full_name": "test/repo"}, "pull_request": {"number": 1, "merged_at": "2026-03-19T10:00:00Z"}, "bounty_amount_usd": 100}'
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `N8N_ENCRYPTION_KEY` | Yes | `changeme-in-production` | Secret key for encrypting n8n credentials |
| `TELEGRAM_CHAT_ID` | Yes | — | Telegram chat ID to send notifications to |
| `N8N_HOST` | No | `localhost` | Hostname n8n listens on |
| `N8N_PORT` | No | `5678` | Port n8n listens on |
| `GENERIC_TIMEZONE` | No | `UTC` | Timezone for scheduled triggers |

## Network Configuration

The n8n container joins the `bounty-hunter-agent_default` Docker network so it can reach the Django API at `http://bounty-hunter-web:8000` (or `http://localhost:8000` from host). Ensure the main stack is running before starting n8n:

```bash
# Start the main stack first
docker compose up -d

# Then start n8n
docker compose -f n8n/docker-compose.yml up -d
```
