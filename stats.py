import os
import sys
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

CLIENT_ID = os.environ.get("CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "")

def api():
    if not (CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN):
        print("\n[ERROR] Missing credentials!")
        print("Please set CLIENT_ID, CLIENT_SECRET, and REFRESH_TOKEN environment variables or put them in the script.\n")
        sys.exit(1)

    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtubeAnalytics", "v2", credentials=creds)

def report(yt, video_id, metrics, dimensions=None, sort=None):
    kwargs = dict(
        ids="channel==MINE",
        startDate="2020-01-01",
        endDate="2035-01-01",
        metrics=metrics,
        filters=f"video=={video_id}",
    )
    if dimensions:
        kwargs["dimensions"] = dimensions
    if sort:
        kwargs["sort"] = sort
    r = yt.reports().query(**kwargs).execute()
    headers = [h["name"] for h in r.get("columnHeaders", [])]
    return headers, r.get("rows", [])

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stats.py <VIDEO_ID>")
        sys.exit(1)

    vid = sys.argv[1]
    yt = api()

    print("=" * 50)
    print(f"ANALYTICS REPORT FOR VIDEO: {vid}")
    print("=" * 50)

    print("\n== TOTALS ==")
    h, rows = report(
        yt, vid,
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,comments,subscribersGained",
    )
    for name, val in zip(h, rows[0] if rows else []):
        print(f"{name}: {val}")

    print("\n== TRAFFIC SOURCES ==")
    h, rows = report(yt, vid, "views",
                     dimensions="insightTrafficSourceType", sort="-views")
    total = sum(r[1] for r in rows) or 1
    for src, v in rows:
        print(f"{src}: {v} ({v / total * 100:.1f}%)")

    print("\n== SEARCH TERMS (TOP 10) ==")
    h, rows = report(yt, vid, "views",
                     dimensions="insightTrafficSourceDetail",
                     sort="-views")
    for term, v in rows[:10]:
        print(f"{term}: {v}")

    print("\n== RETENTION CURVE (sampled) ==")
    h, rows = report(yt, vid, "audienceWatchRatio",
                     dimensions="elapsedVideoTimeRatio", sort="elapsedVideoTimeRatio")
    for ratio, watch in rows[::10]:
        print(f"{float(ratio) * 100:5.0f}% in : {float(watch):.2f}")
    print("=" * 50)
