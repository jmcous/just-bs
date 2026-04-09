# Just BS — Claude Code Onboarding

> *No hot takes. No fluff. No noise. Just the scores for teams you care about.*

---

## What Is Just BS?

Just BS is a personal daily sports digest that runs on a Raspberry Pi and emails the user
every morning with box scores for their teams — and only their teams. The name is a double
meaning: "Just Box Scores" and a commentary on the noise and BS that dominates modern
sports media (hot takes, gambling angles, fantasy hooks, clickbait).

The core philosophy: **facts, patterns, fan pulse. Nothing else.**

This is not a sports alert app. It's an anti-sports-media product for fans who want
to know what actually happened — not what Skip Bayless thinks about it.

---

## Current State (v1 — Live on Raspberry Pi)

Three files. No external dependencies beyond `requests`.

```
just-bs/
├── sports_bot.py   # Main script
├── config.py       # User settings (teams, email, SMTP)
└── README.md
```

### How it works
1. Runs daily via cron at 8 AM
2. Hits the ESPN public JSON API (no key required) for yesterday's scores
3. Filters to only games involving the user's teams (configured in `config.py`)
4. Fetches top statistical performers per game
5. Renders a dark-themed HTML email and sends via SMTP
6. Logs output to `sports_bot.log`

### Leagues supported
- NBA, NFL, MLB (config-driven, easy to add more)

### Key config options (v1)
```python
MY_TEAMS = {
    "NBA": ["Lakers", "Warriors"],
    "NFL": ["Chiefs", "Eagles"],
    "MLB": ["Dodgers", "Yankees"],
}
EMAIL_SUBJECT = "Just BS 🏆"
```

---

## Architecture Principles

- **Config-driven** — all user preferences live in `config.py`, not scattered through code
- **Graceful degradation** — if any feature fails (API down, Claude API error), the email
  still sends with whatever data is available
- **Single daily run** — this is a batch job, not a real-time service. Simplicity is a feature.
- **No external database dependencies** — SQLite only, file lives next to the script
- **Pi-friendly** — low memory, no heavy frameworks, runs on arm64 Ubuntu

---

## Potential Features (Roadmap)

These are planned but not yet built. They are listed in rough priority order.
Each has its own implementation brief or will have one.

---

### 1. Reddit Pulse ⬅ Next Up (see `REDDIT_PULSE.md`)

After each game, scrape the post-game thread from the team's subreddit.
Feed top comments to Claude and generate a 2-3 sentence "fan pulse" summary.
Also surface links to the top 3 posts.

**Why:** Box scores miss things. A benches-clearing fight, a controversial call,
a player saying something wild postgame — none of that shows up in the score.
Reddit post-game threads capture the real story within an hour of the final buzzer.

**Key design constraint:** Must not save Reddit data to disk. Pulse is ephemeral —
generated fresh each morning, included in the email, gone.

---

### 2. AI Game Summaries (Claude-powered)

Use the Anthropic API to generate a 3-5 sentence narrative summary of each game.
Not a recap in the ESPN sense — more like a knowledgeable friend explaining
what happened and why it mattered.

**Already designed and built in v2 (`summarizer.py`)** — needs to be integrated
into the main script and wired to config.

Key prompt philosophy: conversational, no bullet points, reference context naturally,
highlight what was surprising or notable.

---

### 3. Game Memory (SQLite)

Store every game involving the user's teams in a local SQLite database.
At summary time, retrieve relevant history and inject into the Claude prompt:
- Current season W/L record
- Current win/loss streak
- Last N head-to-head matchups between the two teams

**Already designed and built in v2 (`memory.py`)** — needs integration.

**Schema:** Single `games` table. Keyed on ESPN game ID. Stores scores, winner,
top performers, ESPN recap, AI summary, and date.

**Season inference:** NBA/NHL use cross-year seasons ("2024-25"), NFL/MLB use
single year ("2024"). Logic already written in `memory.py`.

---

### 4. Playoff Mode

During postseason, include ALL games for a league — not just the user's teams.
Apply a lighter "report profile" to non-followed teams (less history, no memory save).

**Already designed in v2 (`config.py`)** — `PLAYOFF_MODE` dict per league,
`PLAYOFF_EXTRA_PROFILE` setting, full `REPORT_PROFILES` system.

**Key insight:** ESPN marks postseason games with `season.type == 3`.
Detection logic already written in v2 `sports_bot.py`.

---

### 5. Future Schedule Preview

At the bottom of the email, include upcoming games for the user's teams —
next 3-5 days. Format: "Lakers host the Celtics Thursday · Chiefs at Eagles Sunday."

**Data source:** ESPN scoreboard API returns upcoming games in the same
endpoint as scores — just filter for `status.type.completed == false`.

**Design note:** Keep it brief. This is a preview, not a schedule app.
One line per game, no analysis.

---

### 6. Injury Reports

Surface notable injuries for the user's teams. Relevant before games, not after.
Could gate this behind a "morning preview" mode vs the current "morning recap" mode.

**Data source:** ESPN has injury endpoints but they are less reliable than the
scoreboard API. May need a fallback.

**Design note:** Only surface injuries to key players (starters). Don't list
every day-to-day hamstring. Threshold TBD.

---

## v2 Files (Built, Not Yet Integrated)

These files exist and are designed but haven't been merged into the live v1 codebase:

| File | Purpose |
|---|---|
| `memory.py` | SQLite game history store + context retrieval for Claude prompts |
| `summarizer.py` | Anthropic API calls to generate narrative game summaries |
| `config.py` (v2) | Extended config with profiles, playoff mode, per-team overrides |

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3 | Pi-native, no virtualenv needed for v1 |
| Scores API | ESPN public JSON | No key required, reliable, covers NBA/NFL/MLB |
| Email | SMTP (Gmail App Password) | Configured in config.py |
| AI | Anthropic API (Claude) | Used for summaries and Reddit Pulse distillation |
| Memory | SQLite | File-based, no server, Pi-friendly |
| Reddit | PRAW or raw Reddit JSON API | OAuth required, free tier, personal use |
| Scheduler | cron | Runs at 8 AM daily |
| Host | Raspberry Pi (arm64 Ubuntu) | Always-on, home network |

---

## Constraints & Gotchas

- **Python version:** Use `python3` explicitly in cron — Pi may default to Python 2
- **Reddit API:** Requires OAuth approval for personal use. Rate limit is 60 QPM —
  plenty for personal use, a real constraint at commercial scale
- **ESPN API:** Undocumented public API. No SLA, no key. Has been stable for years
  but could break without notice. Build defensively.
- **Email rendering:** HTML email clients are inconsistent. Stick to inline styles,
  no external CSS, no JavaScript. Test in Gmail.
- **Timezone:** Pi timezone must match the user's local time for 8 AM cron to make sense.
  Set with `sudo timedatectl set-timezone America/New_York`

---

## Voice & Tone (for AI-generated content)

When Claude generates summaries or Reddit Pulse digests, the tone should be:
- Like a knowledgeable friend who watched the game
- Direct and informative, not performative
- No hot takes, no "is X washed?" framing
- Facts and fan sentiment, not editorial opinion
- Short. If it can be said in 3 sentences, don't use 5.
