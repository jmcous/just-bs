#!/usr/bin/env python3
"""
Reddit Pulse — Distill fan sentiment from post-game threads.

After each finished game, scrape the team's subreddit post-game thread,
pull top comments, and use Claude to distill a 2-3 sentence "fan pulse".
Also surface links to the top 3 posts from the subreddit.

Dependencies:
  pip install praw anthropic
"""

import praw
import anthropic
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
    try:
        for submission in subreddit.search(query, sort="new", time_filter="day", limit=5):
            title_lower = submission.title.lower()
            if "post" in title_lower and ("game" in title_lower or "match" in title_lower):
                return submission
    except Exception:
        # If search fails, fall through to strategy 2
        pass

    # Strategy 2: browse new posts from last 24h
    try:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        for submission in subreddit.new(limit=25):
            if datetime.utcfromtimestamp(submission.created_utc) < cutoff:
                break
            title_lower = submission.title.lower()
            if "post" in title_lower and "game" in title_lower:
                return submission
    except Exception:
        pass

    return None


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


def get_top_posts(reddit, subreddit_name: str, limit: int = 3) -> list[dict]:
    """Returns top posts from last 24 hours."""
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    try:
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
    except Exception:
        pass

    return posts


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

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        return ""


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


if __name__ == "__main__":
    result = get_pulse("Lakers", "NBA", "Celtics", won=True, game_date="2026-04-07")
    print("Summary:", result.get("summary"))
    print("Top posts:")
    for p in result.get("top_posts", []):
        print(" •", p["title"])
        print("   ", p["url"])
