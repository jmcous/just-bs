#!/usr/bin/env python3
"""
CLI for managing just-bs subscribers.

Usage:
  python manage.py add-user <email> [<league> <team> ...]
  python manage.py subscribe <email> <league> <team>
  python manage.py unsubscribe <email> <league> <team>
  python manage.py list-users
  python manage.py list-subscriptions <email>
  python manage.py deactivate-user <email>
  python manage.py delete-user <email>

Examples:
  python manage.py add-user jmcous@gmail.com
  python manage.py add-user jmcous@gmail.com NBA Lakers Grizzlies NHL Predators
"""

import sys
import db


def cmd_add_user(email: str, subscriptions: list[tuple[str, str]] = None):
    """Add a new subscriber with optional subscriptions.

    subscriptions: list of (league, team) tuples
    """
    try:
        user_id = db.add_user(email)
        print(f"Added user {email} (id={user_id})")

        if subscriptions:
            for league, team in subscriptions:
                db.add_subscription(user_id, league, team)
                print(f"  Subscribed to {league} — {team}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_subscribe(email: str, league: str, team: str):
    """Subscribe a user to a team."""
    user = db.get_user_by_email(email)
    if not user:
        print(f"Error: User {email} not found", file=sys.stderr)
        sys.exit(1)
    try:
        db.add_subscription(user["id"], league, team)
        print(f"Subscribed {email} to {league} — {team}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_unsubscribe(email: str, league: str, team: str):
    """Unsubscribe a user from a team."""
    user = db.get_user_by_email(email)
    if not user:
        print(f"Error: User {email} not found", file=sys.stderr)
        sys.exit(1)
    try:
        import sqlite3
        from db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM subscriptions
            WHERE user_id = ?
              AND league_id = (SELECT id FROM leagues WHERE name = ?)
              AND team = ?
        """, (user["id"], league, team))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"Unsubscribed {email} from {league} — {team}")
        else:
            print(f"Subscription not found")
        conn.close()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_users():
    """List all active subscribers."""
    users = db.get_active_users()
    if not users:
        print("No active users")
        return
    for user in users:
        print(f"{user['email']} (id={user['id']})")


def cmd_list_subscriptions(email: str):
    """List all subscriptions for a user."""
    user = db.get_user_by_email(email)
    if not user:
        print(f"Error: User {email} not found", file=sys.stderr)
        sys.exit(1)
    subs = db.get_teams_for_user(user["id"])
    if not subs:
        print(f"No subscriptions for {email}")
        return
    for league in sorted(subs.keys()):
        for team in subs[league]:
            print(f"  {league}: {team}")


def cmd_deactivate_user(email: str):
    """Deactivate a user (soft delete)."""
    user = db.get_user_by_email(email)
    if not user:
        print(f"Error: User {email} not found", file=sys.stderr)
        sys.exit(1)
    db.deactivate_user(email)
    print(f"Deactivated {email}")


def cmd_delete_user(email: str):
    """Permanently delete a user and their subscriptions."""
    user = db.get_user_by_email(email)
    if not user:
        print(f"Error: User {email} not found", file=sys.stderr)
        sys.exit(1)
    response = input(f"Permanently delete {email}? Type 'yes' to confirm: ").strip()
    if response.lower() != "yes":
        print("Cancelled")
        return
    db.delete_user(email)
    print(f"Deleted {email}")


def main():
    # Initialize DB with leagues (will be called by sports_bot too)
    from sports_bot import ESPN_ENDPOINTS
    db.init_db(list(ESPN_ENDPOINTS.keys()))

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add-user" and len(sys.argv) >= 3:
        email = sys.argv[2]
        subs = []
        # Parse league/team pairs from remaining args
        remaining = sys.argv[3:]
        for i in range(0, len(remaining), 2):
            if i + 1 < len(remaining):
                subs.append((remaining[i], remaining[i + 1]))
            else:
                print("Error: league/team args must come in pairs", file=sys.stderr)
                sys.exit(1)
        cmd_add_user(email, subs if subs else None)
    elif cmd == "subscribe" and len(sys.argv) == 5:
        cmd_subscribe(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "unsubscribe" and len(sys.argv) == 5:
        cmd_unsubscribe(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "list-users" and len(sys.argv) == 2:
        cmd_list_users()
    elif cmd == "list-subscriptions" and len(sys.argv) == 3:
        cmd_list_subscriptions(sys.argv[2])
    elif cmd == "deactivate-user" and len(sys.argv) == 3:
        cmd_deactivate_user(sys.argv[2])
    elif cmd == "delete-user" and len(sys.argv) == 3:
        cmd_delete_user(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
