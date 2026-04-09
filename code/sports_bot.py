#!/usr/bin/env python3
"""
Just BS  —  Just Box Scores.
            Fetches yesterday's scores for your teams and emails
            you a clean daily digest. That's it.

Dependencies:  pip install requests
API:           Uses the free ESPN hidden JSON API (no key needed)
"""

import json
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── Import user config ──────────────────────────────────────────────────────
try:
    from config import (
        EMAIL_FROM, EMAIL_SUBJECT,
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    )
except ImportError:
    sys.exit("config.py not found. Copy config.py and fill in your settings.")

import db

# Import Reddit Pulse (will skip gracefully if Reddit credentials not configured)
try:
    from reddit_pulse import get_pulse
    REDDIT_PULSE_AVAILABLE = True
except ImportError:
    REDDIT_PULSE_AVAILABLE = False

# ── ESPN API endpoints ──────────────────────────────────────────────────────
ESPN_ENDPOINTS = {
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
}

ESPN_BOXSCORE = {
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary",
}

# Stat columns to display per sport (and per stat group for multi-group sports).
# Keys for NFL/MLB are "{LEAGUE}_{group_name}" as ESPN returns them.
STAT_FILTER = {
    "NBA":           ["MIN", "FG", "3PT", "REB", "AST", "STL", "BLK", "PTS"],
    "NFL_passing":   ["C/ATT", "YDS", "TD", "INT", "RTG"],
    "NFL_rushing":   ["CAR", "YDS", "AVG", "TD"],
    "NFL_receiving": ["REC", "YDS", "AVG", "TD"],
    "NHL":           ["G", "A", "PTS", "+/-", "SOG", "PIM", "TOI"],
    "MLB_batting":   ["AB", "R", "H", "RBI", "BB", "SO"],
    "MLB_pitching":  ["IP", "H", "R", "ER", "BB", "SO"],
}


# ── Data fetching ───────────────────────────────────────────────────────────

def get_yesterday_str():
    yesterday = datetime.now() - timedelta(days=1)
    date_label = f"{yesterday.day} {yesterday.strftime('%b').upper()} {yesterday.year}"
    return yesterday.strftime("%Y%m%d"), date_label


def fetch_scores(league: str, date_str: str) -> list[dict]:
    """Return all games for a league on a given date."""
    url = ESPN_ENDPOINTS[league]
    try:
        r = requests.get(url, params={"dates": date_str}, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("events", [])
    except Exception as e:
        print(f"  WARNING: Could not fetch {league} scores: {e}")
        return []


def team_played(event: dict, my_teams: list[str]) -> bool:
    """Check if any of the user's teams is in this game."""
    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    for comp in competitors:
        team_name  = comp.get("team", {}).get("displayName", "")
        team_short = comp.get("team", {}).get("shortDisplayName", "")
        for my_team in my_teams:
            if my_team.lower() in team_name.lower() or my_team.lower() in team_short.lower():
                return True
    return False


def fetch_box_score(league: str, game_id: str) -> dict:
    """Fetch per-team player stats from ESPN box score.

    Returns:
        {team_abbr: {"name": str, "groups": [{"label": str, "cols": [...], "rows": [...]}]}}
    """
    try:
        r = requests.get(ESPN_BOXSCORE[league], params={"event": game_id}, timeout=10)
        r.raise_for_status()
        data = r.json()

        result = {}
        for team_data in data.get("boxscore", {}).get("players", []):
            team_info = team_data.get("team", {})
            team_abbr = team_info.get("abbreviation", "???")
            team_name = team_info.get("displayName", team_abbr)

            groups = []
            for sg in team_data.get("statistics", []):
                group_type = sg.get("name", "")          # e.g. "passing", "rushing"
                label      = sg.get("displayName", group_type.title())
                all_cols   = sg.get("names", [])

                # Look up the desired columns for this sport/group
                filter_key = f"{league}_{group_type}" if league in ("NFL", "MLB") else league
                desired    = STAT_FILTER.get(filter_key, STAT_FILTER.get(league))

                if desired:
                    # Preserve the order defined in STAT_FILTER
                    col_idx = sorted(
                        [i for i, c in enumerate(all_cols) if c in desired],
                        key=lambda i: desired.index(all_cols[i]),
                    )
                    cols = [all_cols[i] for i in col_idx]
                else:
                    col_idx = list(range(len(all_cols)))
                    cols    = all_cols

                rows = []
                for a in sg.get("athletes", []):
                    all_stats = a.get("stats", [])
                    # Skip players who did not play (all dashes/zeros)
                    if not all_stats or all(s in ("--", "0", "0:00", "") for s in all_stats):
                        continue
                    name  = a.get("athlete", {}).get("shortName", "?")
                    stats = [all_stats[i] if i < len(all_stats) else "--" for i in col_idx]
                    rows.append({"name": name, "stats": stats})

                if rows:
                    groups.append({"label": label, "cols": cols, "rows": rows})

            if groups:
                result[team_abbr] = {"name": team_name, "groups": groups}

        return result
    except Exception:
        return {}


def game_matches_teams(game: dict, my_teams: list[str]) -> bool:
    """Check if a parsed game has any of the user's teams playing."""
    away_name = game["away"]["name"]
    away_abbr = game["away"]["abbr"]
    home_name = game["home"]["name"]
    home_abbr = game["home"]["abbr"]

    for my_team in my_teams:
        my_lower = my_team.lower()
        if (my_lower in away_name.lower() or my_lower in away_abbr.lower() or
            my_lower in home_name.lower() or my_lower in home_abbr.lower()):
            return True
    return False


def parse_game(event: dict, league: str) -> dict:
    """Extract the key details from an ESPN event object."""
    comp        = event.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    status      = event.get("status", {}).get("type", {})

    teams = []
    for c in competitors:
        teams.append({
            "name":   c.get("team", {}).get("displayName", "TBD"),
            "abbr":   c.get("team", {}).get("abbreviation", ""),
            "score":  c.get("score", "--"),
            "winner": c.get("winner", False),
            "record": c.get("records", [{}])[0].get("summary", "") if c.get("records") else "",
        })

    # ESPN: away=index 0, home=index 1
    if len(teams) == 2:
        away, home = teams[0], teams[1]
    else:
        away = home = {"name": "TBD", "abbr": "", "score": "--", "winner": False, "record": ""}

    return {
        "id":        event.get("id", ""),
        "name":      event.get("name", ""),
        "status":    status.get("description", ""),
        "finished":  status.get("completed", False),
        "away":      away,
        "home":      home,
        "box_score": {},
    }


# ── HTML email builder ──────────────────────────────────────────────────────

# Terminal color palette
C_BRIGHT  = "#00ff00"   # bright green  — winner scores, player names
C_MID     = "#00cc00"   # mid green     — normal text, non-winner scores
C_DIM     = "#007700"   # dim green     — labels, headers
C_DIMMER  = "#004400"   # very dim      — separators, records
C_WHITE   = "#e0e0e0"   # near-white    — winner score emphasis
BG        = "#000000"   # black bg


def _stat_table_html(label: str, cols: list[str], rows: list[dict]) -> str:
    """Render one player stat group as a terminal-style HTML table."""
    hdr_cells = (
        f'<td style="padding:1px 10px 1px 0;color:{C_DIM};'
        f'font-size:11px;white-space:nowrap">PLAYER</td>'
    )
    for col in cols:
        hdr_cells += (
            f'<td style="padding:1px 5px;color:{C_DIM};font-size:11px;'
            f'text-align:right;white-space:nowrap">{col}</td>'
        )

    data_rows = ""
    for row in rows:
        data_rows += (
            f'<tr><td style="padding:1px 10px 1px 0;color:{C_MID};'
            f'font-size:12px;white-space:nowrap">{row["name"]}</td>'
        )
        for stat in row["stats"]:
            data_rows += (
                f'<td style="padding:1px 5px;color:{C_MID};font-size:12px;'
                f'text-align:right;white-space:nowrap">{stat}</td>'
            )
        data_rows += "</tr>"

    return f"""
    <div style="margin:10px 0 2px;font-size:10px;color:{C_DIMMER};
                text-transform:uppercase;letter-spacing:1px;
                font-family:'Courier New',Courier,monospace">{label}</div>
    <table style="border-collapse:collapse;
                  font-family:'Courier New',Courier,monospace;
                  margin-bottom:14px">
      <tr>{hdr_cells}</tr>
      {data_rows}
    </table>"""


def build_email_html(games_by_league: dict, date_label: str) -> str:
    """Render a terminal-style HTML email."""

    def score_row(team: dict) -> str:
        if team["winner"]:
            indicator = f'<span style="color:{C_DIM}">&gt;&gt;</span> '
            name_col  = f'<span style="color:{C_BRIGHT};font-weight:bold">{team["name"]}</span>'
            rec_col   = (f'<span style="color:{C_DIMMER};font-size:11px"> ({team["record"]})</span>'
                         if team["record"] else "")
            score_col = f'<span style="color:{C_BRIGHT};font-weight:bold">{team["score"]}</span>'
        else:
            indicator = '&nbsp;&nbsp;&nbsp;'
            name_col  = f'<span style="color:{C_MID}">{team["name"]}</span>'
            rec_col   = (f'<span style="color:{C_DIMMER};font-size:11px"> ({team["record"]})</span>'
                         if team["record"] else "")
            score_col = f'<span style="color:{C_DIM}">{team["score"]}</span>'

        return f"""
        <tr>
          <td style="padding:3px 12px 3px 0;white-space:nowrap">
            {indicator}{name_col}{rec_col}
          </td>
          <td style="padding:3px 0;text-align:right;white-space:nowrap">
            {score_col}
          </td>
        </tr>"""

    sections = ""
    total_games = 0

    for league, games in games_by_league.items():
        if not games:
            continue

        cards = ""
        for g in games:
            total_games += 1
            away, home = g["away"], g["home"]
            status_txt = g["status"].upper()
            sep = f'<div style="color:{C_DIMMER};font-size:12px">{"=" * 60}</div>'

            # Score block
            score_block = f"""
            <table style="width:100%;border-collapse:collapse;
                           font-family:'Courier New',Courier,monospace;
                           margin:6px 0 10px">
              {score_row(away)}
              {score_row(home)}
            </table>"""

            # Box score block: away team first, then home
            box_html = ""
            bs = g.get("box_score", {})
            for abbr in (away["abbr"], home["abbr"]):
                team_bs = bs.get(abbr)
                if not team_bs:
                    continue
                box_html += (
                    f'<div style="margin-top:12px;color:{C_DIM};font-size:11px;'
                    f'font-family:\'Courier New\',Courier,monospace;'
                    f'text-transform:uppercase;letter-spacing:1px">'
                    f'--- {team_bs["name"]} ---</div>'
                )
                for group in team_bs["groups"]:
                    box_html += _stat_table_html(group["label"], group["cols"], group["rows"])

            # Reddit Pulse block (if available)
            pulse_html = ""
            if g.get("pulse"):
                pulse = g["pulse"]
                summary = pulse.get("summary", "")
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

                if summary or top_posts:
                    pulse_html = f"""
                <div style="margin-top:14px;border-top:1px solid #22224a;padding-top:14px">
                  <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;
                               color:#666;margin-bottom:8px">Reddit Pulse</div>
                  <p style="margin:0;font-size:13px;color:#c0b8ff;line-height:1.6;font-style:italic">
                    {summary if summary else "No comments found on post-game thread."}
                  </p>
                  {posts_html}
                </div>"""

            cards += f"""
            <div style="margin-bottom:24px">
              {sep}
              <div style="display:flex;justify-content:space-between;
                           font-family:'Courier New',Courier,monospace;
                           font-size:11px;margin:4px 0">
                <span style="color:{C_DIM}">[{league}]</span>
                <span style="color:{C_DIMMER}">[{status_txt}]</span>
              </div>
              {score_block}
              {box_html}
              {pulse_html}
            </div>"""

        sections += f"""
        <div style="margin-bottom:16px">
          {cards}
        </div>"""

    if total_games == 0:
        sections = f"""
        <div style="text-align:center;padding:40px;
                    font-family:'Courier New',Courier,monospace;color:{C_DIM}">
          &gt; None of your teams played yesterday.
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:{BG};
             font-family:'Courier New',Courier,monospace;color:{C_MID}">
  <div style="max-width:680px;margin:0 auto;padding:24px 16px">

    <!-- Header -->
    <div style="padding:20px 0 16px;border-bottom:1px solid {C_DIMMER};
                margin-bottom:24px">
      <div style="font-size:22px;font-weight:bold;color:{C_BRIGHT};
                  letter-spacing:2px">JUST BS</div>
      <div style="font-size:11px;color:{C_DIM};margin-top:4px;
                  letter-spacing:1px">JUST BOX SCORES.</div>
      <div style="font-size:12px;color:{C_DIMMER};margin-top:6px">{date_label}</div>
    </div>

    <!-- Game cards -->
    {sections}

    <!-- Footer -->
    <div style="padding-top:16px;border-top:1px solid {C_DIMMER};
                font-size:11px;color:{C_DIMMER};
                font-family:'Courier New',Courier,monospace">
      just-bs &middot; scores via espn &middot
    </div>

  </div>
</body>
</html>"""


# ── Email sender ────────────────────────────────────────────────────────────

def send_email(html: str, date_label: str, to: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{EMAIL_SUBJECT} -- {date_label}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, to, msg.as_string())
    print(f"Email sent to {to}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # Initialize database with current leagues
    db.init_db(list(ESPN_ENDPOINTS.keys()))

    date_str, date_label = get_yesterday_str()
    print(f"Fetching scores for {date_label} ...")

    # Fetch and parse all games for all leagues (one API call per league)
    all_games_by_league = {}
    for league in ESPN_ENDPOINTS.keys():
        print(f"  {league} ...", end=" ", flush=True)
        events = fetch_scores(league, date_str)
        all_games_by_league[league] = [parse_game(e, league) for e in events]
        print(f"({len(all_games_by_league[league])} games)")

    # Fetch box scores for all finished games (cached for all users)
    print("Fetching box scores ...")
    total_bs_fetched = 0
    for league in all_games_by_league:
        for game in all_games_by_league[league]:
            if game["finished"]:
                game["box_score"] = fetch_box_score(league, game["id"])
                total_bs_fetched += 1
    print(f"  {total_bs_fetched} box score(s) fetched")

    # Send emails to each active user
    users = db.get_active_users()
    if not users:
        print("No active subscribers. Use manage.py to add users.")
        return

    for user in users:
        print(f"\nPreparing email for {user['email']} ...")
        my_teams = db.get_teams_for_user(user["id"])

        # Filter games to only those matching user's subscribed teams
        games_by_league = {}
        for league in my_teams.keys():
            if league not in all_games_by_league:
                continue
            my_games = [
                game for game in all_games_by_league[league]
                if game_matches_teams(game, my_teams[league])
            ]
            if my_games:
                games_by_league[league] = my_games
                print(f"  {league}: {len(my_games)} game(s) matched")

        # Fetch Reddit Pulse for finished games (if enabled and available)
        if REDDIT_PULSE_AVAILABLE:
            try:
                from config import REDDIT_PULSE_ENABLED
                if REDDIT_PULSE_ENABLED:
                    for league, games in games_by_league.items():
                        for game in games:
                            if game["finished"]:
                                # Determine which team is mine and which is opponent
                                away_name = game["away"]["name"]
                                home_name = game["home"]["name"]
                                my_team_list = my_teams.get(league, [])

                                away_is_mine = any(
                                    t.lower() in away_name.lower() or t.lower() in game["away"]["abbr"].lower()
                                    for t in my_team_list
                                )
                                home_is_mine = any(
                                    t.lower() in home_name.lower() or t.lower() in game["home"]["abbr"].lower()
                                    for t in my_team_list
                                )

                                if away_is_mine and not home_is_mine:
                                    my_team = away_name
                                    opponent = home_name
                                    won = game["away"]["winner"]
                                elif home_is_mine and not away_is_mine:
                                    my_team = home_name
                                    opponent = away_name
                                    won = game["home"]["winner"]
                                else:
                                    # Shouldn't happen, but skip if we can't determine teams
                                    game["pulse"] = {}
                                    continue

                                game["pulse"] = get_pulse(my_team, league, opponent, won, date_str)
            except Exception as e:
                print(f"  ⚠  Could not fetch Reddit Pulse: {e}")

        html = build_email_html(games_by_league, date_label)
        send_email(html, date_label, to=user["email"])


if __name__ == "__main__":
    main()
