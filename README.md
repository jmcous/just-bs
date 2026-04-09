# Just BS — Just Box Scores

No hot takes. No fluff. No noise. Just the scores for teams you care about, in your inbox every morning.

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install requests anthropic praw
```

Dependencies:
- `requests` — ESPN API calls
- `anthropic` — Claude API for Reddit Pulse summaries
- `praw` — Reddit API wrapper (for Reddit Pulse feature)

### 2. Copy and configure `config.py`
```bash
cp code/config.py.example code/config.py
```
Then edit `code/config.py` and fill in:
- **EMAIL_FROM** — sender email address
- **EMAIL_SUBJECT** — email subject line
- **SMTP settings** — see provider guide below
- **REDDIT_CLIENT_ID** and **REDDIT_CLIENT_SECRET** — (optional, see Reddit Pulse setup)

### 3. Add your first subscriber
```bash
python manage.py add-user your-email@example.com NBA Lakers Grizzlies NHL Predators
```

This adds you as a subscriber and subscribes you to:
- NBA: Lakers, Grizzlies
- NHL: Predators

### 4. Test it
```bash
python sports_bot.py
```

### 5. Schedule it (daily at 8 AM)
```bash
crontab -e
```
Add this line:
```
0 8 * * * cd /path/to/sports_bot && python sports_bot.py >> sports_bot.log 2>&1
```

---

## Email Provider Setup

### Gmail (recommended)
1. Enable 2-factor authentication on your Google account
2. Go to **Google Account → Security → App Passwords**
3. Generate an App Password for "Mail"
4. Use that 16-character password as `SMTP_PASS` in config.py

```python
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "you@gmail.com"
SMTP_PASS = "xxxx xxxx xxxx xxxx"   # App Password
```

### Outlook / Hotmail
```python
SMTP_HOST = "smtp-mail.outlook.com"
SMTP_PORT = 587
```

### Yahoo Mail
```python
SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 587
```

### Custom/Self-hosted SMTP
Just fill in your server's host, port, username, and password.

---

## Reddit Pulse Setup (Optional)

Reddit Pulse distills fan sentiment from post-game threads. After each finished game, it pulls the top comments from your team's subreddit, feeds them to Claude, and includes a 2-3 sentence "fan pulse" summary plus links to the top 3 posts in the email.

**To enable Reddit Pulse:**

1. **Create a Reddit OAuth app:**
   - Go to https://www.reddit.com/prefs/apps
   - Click "Create App" (type: **script**)
   - Name: anything (e.g., "just-bs-personal")
   - Redirect URI: `http://localhost:8080`

2. **Add to `config.py`:**
   ```python
   REDDIT_CLIENT_ID     = "your_client_id"
   REDDIT_CLIENT_SECRET = "your_client_secret"
   REDDIT_USER_AGENT    = "just-bs-personal/1.0"
   
   TEAM_SUBREDDITS = {
       "Lakers":   "lakers",
       "Warriors": "warriors",
       "Chiefs":   "kansascitychiefs",
       # Add your teams here
   }
   
   REDDIT_PULSE_ENABLED = True
   ```

3. **Set your Anthropic API key:**
   ```bash
   export ANTHROPIC_API_KEY="sk-..."
   ```

If Reddit Pulse isn't configured, the script gracefully skips it and still sends the email normally.

See [REDDIT_PULSE.md](REDDIT_PULSE.md) for implementation details.

---

## Managing Subscribers

All subscriber data lives in `data/justbs.db` (auto-created on first run).

### Add a subscriber with multiple subscriptions
```bash
python manage.py add-user alice@example.com NBA Lakers Celtics NFL Chiefs
```

### Add a subscriber (no subscriptions yet)
```bash
python manage.py add-user alice@example.com
```

### Subscribe to additional teams
```bash
python manage.py subscribe alice@example.com MLB Braves
```

### View all subscribers
```bash
python manage.py list-users
```

### View one subscriber's subscriptions
```bash
python manage.py list-subscriptions alice@example.com
```

### Deactivate (soft delete) a subscriber
```bash
python manage.py deactivate-user alice@example.com
```

### Delete a subscriber permanently
```bash
python manage.py delete-user alice@example.com
```

---

## Team Name Tips

Team names are matched **flexibly** — partial names work. Use the city name, nickname, or any substring of the full team name. For example:

- "Lakers" or "Lakers" (matches Los Angeles Lakers)
- "49ers" or "San Francisco" (matches San Francisco 49ers)  
- "Yankees" or "New York" (matches New York Yankees)

Supported leagues: **NBA**, **NFL**, **NHL**, **MLB**

---

## What the Email Looks Like

- Terminal-style dark background with bright green text (`#00ff00`)
- Monospace (Courier New) font — clean, no-fluff aesthetic
- One section per league, one card per game
- Final score + record for each team
- Full player box score stats (filtered by sport)
- "None of your teams played yesterday" message on off days

---

## Files

| File | Purpose |
|------|---------|
| `code/sports_bot.py` | Main script — fetches scores, sends emails |
| `code/config.py.example` | Config template (copy to `config.py` and fill in) |
| `code/config.py` | SMTP & Reddit settings (gitignored, keep secrets here) |
| `code/db.py` | SQLite database layer |
| `code/manage.py` | CLI for managing subscribers |
| `code/reddit_pulse.py` | Reddit Pulse feature — fan sentiment from post-game threads |
| `data/justbs.db` | Subscriber database (auto-created, gitignored) |
| `REDDIT_PULSE.md` | Reddit Pulse implementation details |
| `ONBOARDING.md` | Project roadmap and architecture |
| `README.md` | This file |

---

## Supported Leagues & Stats

**NBA** — MIN, FG, 3PT, REB, AST, STL, BLK, PTS

**NFL** — Passing (C/ATT, YDS, TD, INT, RTG) / Rushing (CAR, YDS, AVG, TD) / Receiving (REC, YDS, AVG, TD)

**NHL** — G, A, PTS, +/-, SOG, PIM, TOI

**MLB** — Batting (AB, R, H, RBI, BB, SO) / Pitching (IP, H, R, ER, BB, SO)

---

## Data Source

Uses the free ESPN public JSON API — no API key required.
