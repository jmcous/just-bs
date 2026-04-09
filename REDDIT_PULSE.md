# Reddit Pulse — Implementation Brief

> Feature brief for Claude Code. Read `ONBOARDING.md` first for full project context.

---

## What Is Reddit Pulse?

After each game, find the post-game thread on the team's subreddit, pull the top
comments, and use Claude to distill a 2-3 sentence "fan pulse" — what the fanbase
actually thought about what happened. Also surface links to the top 3 posts.

**The problem it solves:** Box scores miss things. A benches-clearing fight,
a blown call, a player saying something wild postgame — none of that shows up
in the final score. Reddit post-game threads capture the real story within
an hour of the final buzzer, in the unfiltered voice of actual fans.

---

## Desired Output in the Email

Each game card that currently shows score + top performers should gain a new section:

```
── Reddit Pulse ────────────────────────────────
Fans were stunned by the benches-clearing incident in the 6th inning — most
threads focused on the ejection rather than the loss itself. General mood is
frustrated but not panicked given the division lead.

Top posts:
  • [Post-Game Thread: Braves 4, Phillies 7] → reddit.com/r/Braves/...
  • [The Olson ejection was complete BS] → reddit.com/r/Braves/...
  • [Series recap: we need to talk about the bullpen] → reddit.com/r/Braves/...
────────────────────────────────────────────────
```

---

## Implementation Plan

### New file: `reddit_pulse.py`

Keep Reddit logic fully isolated from the main script. The main script calls
`get_pulse(team, league, game_date)` and gets back a dict. It doesn't need to
know anything about Reddit internals.

---

### Step 1: Reddit Authentication

Use the `praw` library (Python Reddit API Wrapper).

```bash
pip install praw
```

User needs to create a Reddit app at https://www.reddit.com/prefs/apps
- Type: **script**
- Name: anything (e.g. "just-bs-personal")
- Redirect URI: http://localhost:8080

Add to `config.py`:
```python
# Reddit API (for Reddit Pulse feature)
REDDIT_CLIENT_ID     = "your_client_id"
REDDIT_CLIENT_SECRET = "your_client_secret"
REDDIT_USER_AGENT    = "just-bs-personal-bot/1.0"
```

---

### Step 2: Subreddit Mapping

Add to `config.py`:
```python
TEAM_SUBREDDITS = {
    # NBA
    "Lakers":   "lakers",
    "Warriors": "warriors",
    "Celtics":  "bostonceltics",
    "Knicks":   "nyknicks",
    # NFL
    "Chiefs":   "kansascitychiefs",
    "Eagles":   "eagles",
    "Patriots": "Patriots",
    # MLB
    "Dodgers":  "dodgers",
    "Yankees":  "NYYankees",
    "Braves":   "Braves",
    "Mets":     "NewYorkMets",
    # Add more as needed
}
```

The user should extend this for their specific teams. If a team isn't in the
mapping, Reddit Pulse is silently skipped for that game — don't error out.

---

### Step 3: Find the Post-Game Thread

Post-game threads are consistently titled. Search the subreddit for recent
posts matching the pattern.

```python
import praw
from datetime import datetime, timedelta

def find_postgame_thread(reddit, subreddit_name: str, opponent: str, game_date: str) -> praw.models.Submission | None:
    """
    Search for the post-game thread. Tries two strategies:
    1. Search subreddit for 'post game thread' + opponent name
    2. Browse 'new' posts from the last 24 hours as fallback
    """
    subreddit = reddit.subreddit(subreddit_name)

    # Strategy 1: search
    query = f"post game thread {opponent}"
    for submission in subreddit.search(query, sort="new", time_filter="day", limit=5):
        title_lower = submission.title.lower()
        if "post" in title_lower and ("game" in title_lower or "match" in title_lower):
            return submission

    # Strategy 2: browse new posts from last 24h
    cutoff = datetime.utcnow() - timedelta(hours=24)
    for submission in subreddit.new(limit=25):
        if datetime.utcfromtimestamp(submission.created_utc) < cutoff:
            break
        title_lower = submission.title.lower()
        if "post" in title_lower and "game" in title_lower:
            return submission

    return None
```

---

### Step 4: Pull Top Comments

```python
def get_top_comments(submission: praw.models.Submission, limit: int = 15) -> list[str]:
    """
    Pull top-level comments sorted by score.
    Skip AutoModerator, score requirement posts, and very short comments.
    """
    submission.comment_sort = "top"
    submission.comments.replace_more(limit=0)  # flatten MoreComments

    comments = []
    for comment in submission.comments[:limit]:
        if comment.author and comment.author.name == "AutoModerator":
            continue
        if len(comment.body) < 20:
            continue
        comments.append(comment.body)

    return comments[:limit]
```

---

### Step 5: Top 3 Posts from Subreddit

In addition to the post-game thread, surface the top 3 posts from the last 24 hours
on the subreddit — these often capture reactions, highlights, or controversies the
post-game thread misses.

```python
def get_top_posts(reddit, subreddit_name: str, limit: int = 3) -> list[dict]:
    """Returns top posts from last 24 hours."""
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    for submission in subreddit.top(time_filter="day", limit=limit + 5):
        if submission.stickied:
            continue
        posts.append({
            "title": submission.title,
            "url":   f"https://reddit.com{submission.permalink}",
            "score": submission.score,
        })
        if len(posts) >= limit:
            break
    return posts
```

---

### Step 6: Claude Pulse Summary

Feed the top comments to Claude. Keep the prompt tight — we want distillation,
not analysis.

```python
import anthropic

def generate_pulse(comments: list[str], team: str, opponent: str, won: bool) -> str:
    """Generate a 2-3 sentence fan pulse from top Reddit comments."""
    result = "won" if won else "lost"
    comments_text = "\n---\n".join(comments[:12])

    prompt = f"""These are top comments from r/{team}'s post-game thread after they {result} to {opponent}.

{comments_text}

Write 2-3 sentences summarizing the overall fan reaction and mood. Focus on:
- What fans thought about the result
- Any specific plays, calls, or moments dominating discussion
- The general emotional tone (frustrated, excited, concerned, etc.)

Be direct. No bullet points. Do not start with "Fans" or "The fanbase". Write it like a one-paragraph
field report from inside the subreddit."""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
```

---

### Step 7: Main interface function

```python
def get_pulse(team: str, league: str, opponent: str, won: bool, game_date: str) -> dict:
    """
    Main entry point. Returns a pulse dict or empty dict if pulse unavailable.

    Return shape:
    {
        "summary": "2-3 sentence Claude summary...",
        "top_posts": [
            {"title": "...", "url": "https://reddit.com/..."},
            ...
        ]
    }
    """
    from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, TEAM_SUBREDDITS

    subreddit_name = TEAM_SUBREDDITS.get(team)
    if not subreddit_name:
        print(f"  ℹ  No subreddit mapped for {team}, skipping pulse")
        return {}

    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )

        thread   = find_postgame_thread(reddit, subreddit_name, opponent, game_date)
        comments = get_top_comments(thread) if thread else []
        posts    = get_top_posts(reddit, subreddit_name)

        summary = ""
        if comments:
            summary = generate_pulse(comments, subreddit_name, opponent, won)

        return {"summary": summary, "top_posts": posts}

    except Exception as e:
        print(f"  ⚠  Reddit Pulse failed for {team}: {e}")
        return {}  # never crash the main email send
```

---

### Step 8: Wire into `sports_bot.py`

In `process_game()`, after fetching performers, add:

```python
from reddit_pulse import get_pulse

# Reddit Pulse — only for finished games involving my teams
if game["finished"] and game["is_my_team"]:
    my_team  = game["away"]["name"] if game["away"]["is_my_team"] else game["home"]["name"]
    opponent = game["home"]["name"] if game["away"]["is_my_team"] else game["away"]["name"]
    won      = game["away"]["winner"] if game["away"]["is_my_team"] else game["home"]["winner"]
    game["pulse"] = get_pulse(my_team, league, opponent, won, date_iso)
else:
    game["pulse"] = {}
```

---

### Step 9: Render in email HTML

In `build_email_html()`, inside each game card, after `performers_html`:

```python
pulse_html = ""
if g.get("pulse"):
    pulse     = g["pulse"]
    summary   = pulse.get("summary", "")
    top_posts = pulse.get("top_posts", [])

    posts_html = ""
    if top_posts:
        links = "".join(
            f'<li style="margin:4px 0"><a href="{p["url"]}" '
            f'style="color:#ff6b35;font-size:12px;text-decoration:none">'
            f'{p["title"][:70]}{"…" if len(p["title"]) > 70 else ""}</a></li>'
            for p in top_posts
        )
        posts_html = f'<ul style="margin:8px 0 0;padding-left:16px">{links}</ul>'

    pulse_html = f"""
    <div style="margin-top:14px;border-top:1px solid #22224a;padding-top:14px">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
                   color:#666;margin-bottom:8px">Reddit Pulse</div>
      <p style="margin:0;font-size:13px;color:#c0b8ff;line-height:1.6;font-style:italic">
        {summary}
      </p>
      {posts_html}
    </div>"""
```

---

## Config additions summary

Add these to `config.py`:

```python
# ── Reddit Pulse ──────────────────────────────────────────────────────────────
REDDIT_CLIENT_ID     = "your_client_id"
REDDIT_CLIENT_SECRET = "your_client_secret"
REDDIT_USER_AGENT    = "just-bs-personal/1.0"

TEAM_SUBREDDITS = {
    "Lakers":   "lakers",
    "Warriors": "warriors",
    "Chiefs":   "kansascitychiefs",
    "Eagles":   "eagles",
    "Dodgers":  "dodgers",
    "Yankees":  "NYYankees",
    # Add your teams here
}

# Set to False to disable Reddit Pulse entirely
REDDIT_PULSE_ENABLED = True
```

---

## Error handling rules

- If Reddit auth fails → skip pulse, log warning, email sends normally
- If no post-game thread found → skip summary, still show top 3 posts if available
- If Claude API fails → skip summary, still show top 3 posts
- If subreddit not in mapping → skip silently
- **Never let Reddit Pulse crash the email send**

---

## Dependencies

```bash
pip install praw anthropic
```

---

## Testing

Test Reddit Pulse in isolation before wiring into the main script:

```bash
python reddit_pulse.py
```

Add a `__main__` block to `reddit_pulse.py` for this:

```python
if __name__ == "__main__":
    result = get_pulse("Lakers", "NBA", "Celtics", won=True, game_date="2026-04-07")
    print("Summary:", result.get("summary"))
    print("Top posts:")
    for p in result.get("top_posts", []):
        print(" •", p["title"])
        print("   ", p["url"])
```
