# Building a Free YouTube Analytics Connector for Claude

Goal: stop taking screenshots. Ask "how is the fuse doing?" and have Claude
fetch the numbers itself.

Everything here is free. The YouTube Analytics API costs nothing, and the
hosting options listed have free tiers.

---

## Three levels — pick where to stop

| Level | What you get | Setup |
|---|---|---|
| **0. CSV export** | One file instead of four screenshots | 1 click, today |
| **1. Local script** | Run a command, paste the text into chat | ~1 hour |
| **2. MCP connector** | Claude fetches the numbers itself | ~2-3 hours |

Levels 1 and 2 share the same Google setup and the same API code. Level 2 is
only a web wrapper around level 1, so doing level 1 first is never wasted work.

**Do level 0 now regardless.** In YouTube Studio open a video's analytics,
click **Advanced mode**, then the export button (top right), and choose CSV.
That already solves most of the annoyance.

---

## Part A — Google Cloud setup (needed for levels 1 and 2)

This is the fiddly part. It is free and you only do it once.

### A1. Create a project
1. Go to `https://console.cloud.google.com`
2. Create a new project, name it something like `yt-analytics`.
3. No billing account is needed.

### A2. Enable the API
1. In the console, open **APIs & Services > Library**.
2. Enable **YouTube Analytics API**.
3. Optionally also enable **YouTube Data API v3** (useful for looking up a
   video's title from its ID).

### A3. Configure the OAuth consent screen
1. **APIs & Services > OAuth consent screen**.
2. User type: **External**. (Internal is only for Workspace organisations.)
3. Fill in the app name and your email.
4. Add the scope: `https://www.googleapis.com/auth/yt-analytics.readonly`
   (read-only — the connector can never change anything on your channel).
5. Under **Test users**, add the Google account that owns the channel.
6. Leave the app in **Testing** mode. You do not need Google verification for
   personal use.

> **The one gotcha:** in Testing mode, refresh tokens expire after **7 days**.
> That means re-running the auth step weekly. To avoid this, click
> **Publish app** on the consent screen. Because your only scope is a
> read-only analytics scope for your own account, publishing is allowed and
> the token then lasts until you revoke it. You may see an "unverified app"
> warning when you authorise; that is expected for a personal app.

### A4. Create credentials
1. **APIs & Services > Credentials > Create credentials > OAuth client ID**.
2. Application type: **Desktop app**.
3. Download the JSON. Keep it private — it is a key to your account.

### A5. Get a refresh token
Run this once on your machine. It opens a browser, you approve, and it prints
a refresh token you will reuse forever.

```bash
pip install google-auth-oauthlib google-api-python-client
```

```python
# get_token.py
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=8080)

print("CLIENT_ID:    ", creds.client_id)
print("CLIENT_SECRET:", creds.client_secret)
print("REFRESH_TOKEN:", creds.refresh_token)
```

Save those three values. They are all the server needs.

---

## Part B — Level 1: the local script

```bash
pip install google-auth google-api-python-client
```

```python
# stats.py  —  usage: python stats.py VIDEO_ID
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CLIENT_ID     = "..."
CLIENT_SECRET = "..."
REFRESH_TOKEN = "..."

def api():
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
    vid = sys.argv[1]
    yt = api()

    print("== TOTALS ==")
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

    print("\n== SEARCH TERMS ==")
    h, rows = report(yt, vid, "views",
                     dimensions="insightTrafficSourceDetail",
                     sort="-views")
    for term, v in rows[:10]:
        print(f"{term}: {v}")

    print("\n== RETENTION CURVE ==")
    h, rows = report(yt, vid, "audienceWatchRatio",
                     dimensions="elapsedVideoTimeRatio", sort="elapsedVideoTimeRatio")
    for ratio, watch in rows[::10]:       # every 10th point
        print(f"{float(ratio) * 100:5.0f}% in : {float(watch):.2f}")
```

Run `python stats.py <video_id>` and paste the output to me. This alone
replaces the screenshots.

**Useful metrics:** `views`, `estimatedMinutesWatched`, `averageViewDuration`,
`averageViewPercentage`, `likes`, `comments`, `shares`, `subscribersGained`.

**Useful dimensions:** `day`, `insightTrafficSourceType`,
`insightTrafficSourceDetail`, `deviceType`, `country`, `elapsedVideoTimeRatio`
(retention), `subscribedStatus`.

**Note on Shorts:** the API has no "swiped away" or "qualified Shorts views"
metric. Those exist only in Studio. `averageViewPercentage` is the closest
stand-in for the stayed-to-watch number.

---

## Part C — Level 2: the MCP connector

### How Claude connects
Claude.ai reaches your server **from Anthropic's cloud**, not from your
computer. So the server must be on a **public HTTPS URL**. A server running
only on `localhost` cannot be added as a custom connector here. Claude
supports **Streamable HTTP** (recommended) and the older SSE transport, and
works with authless or OAuth servers.

Custom connectors are available on paid plans (Pro, Max, Team, Enterprise).

### The server

```bash
pip install "mcp[cli]" google-auth google-api-python-client
```

```python
# server.py
import os
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

mcp = FastMCP("YouTube Analytics")

def api():
    creds = Credentials(
        None,
        refresh_token=os.environ["REFRESH_TOKEN"],
        client_id=os.environ["CLIENT_ID"],
        client_secret=os.environ["CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtubeAnalytics", "v2", credentials=creds)

def query(metrics, dimensions=None, filters=None, sort=None,
          start="2020-01-01", end="2035-01-01"):
    kwargs = dict(ids="channel==MINE", startDate=start, endDate=end,
                  metrics=metrics)
    if dimensions: kwargs["dimensions"] = dimensions
    if filters:    kwargs["filters"] = filters
    if sort:       kwargs["sort"] = sort
    r = api().reports().query(**kwargs).execute()
    headers = [h["name"] for h in r.get("columnHeaders", [])]
    return {"headers": headers, "rows": r.get("rows", [])}

@mcp.tool()
def video_stats(video_id: str) -> dict:
    """Totals for one video: views, watch time, average view duration and
    percentage, likes, comments, subscribers gained."""
    return query(
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,comments,subscribersGained",
        filters=f"video=={video_id}",
    )

@mcp.tool()
def traffic_sources(video_id: str) -> dict:
    """Where the views came from (Shorts feed, search, suggested, etc.)."""
    return query("views", dimensions="insightTrafficSourceType",
                 filters=f"video=={video_id}", sort="-views")

@mcp.tool()
def search_terms(video_id: str) -> dict:
    """The search queries that led to this video."""
    return query("views", dimensions="insightTrafficSourceDetail",
                 filters=f"video=={video_id}", sort="-views")

@mcp.tool()
def retention(video_id: str) -> dict:
    """Retention curve: 100 points of audienceWatchRatio across the video."""
    return query("audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                 filters=f"video=={video_id}", sort="elapsedVideoTimeRatio")

@mcp.tool()
def channel_totals(start_date: str, end_date: str) -> dict:
    """Channel-wide totals between two dates (YYYY-MM-DD)."""
    return query("views,estimatedMinutesWatched,subscribersGained",
                 start=start_date, end=end_date)

@mcp.tool()
def top_videos(start_date: str, end_date: str) -> dict:
    """Best performing videos in a date range."""
    return query("views,averageViewPercentage", dimensions="video",
                 start=start_date, end=end_date, sort="-views")

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### Free hosting options
Any of these can serve a public HTTPS endpoint for free:

- **Hugging Face Spaces** — simplest for Python. Free CPU tier, gives you an
  HTTPS URL, and has a built-in secrets UI for the three credentials. Free
  Spaces sleep when idle and wake on the next request.
- **Deno Deploy / Cloudflare Workers** — solid free tiers, but they run
  JavaScript, so the server would need rewriting with the TypeScript MCP SDK.
- **Fly.io / Railway / Render** — small free or trial allowances that change
  often. Check current terms before relying on them.

Put `CLIENT_ID`, `CLIENT_SECRET` and `REFRESH_TOKEN` in the host's
**secrets/environment variables**. Never commit them to a repo.

### Adding it to Claude
1. Settings (or Customize) > **Connectors**.
2. **Add custom connector**.
3. Paste your server URL, e.g. `https://your-space.hf.space/mcp`.
4. Add.

Then ask: *"What are the traffic sources for video ABC123?"*

---

## Security — read this before hosting

An authless server on a public URL means **anyone who learns the URL can read
your channel analytics**. The data is read-only and low-risk, but it is still
yours. Reasonable mitigations:

- Put a long random string in the path, e.g. `/mcp-7f3a9c2b51e0/`. Obscurity,
  not real security, but it stops casual discovery.
- Better: check a shared secret inside each tool call, or add proper OAuth if
  you want to do it correctly.
- Never put the refresh token in the code. Environment variables only.
- If a token leaks, revoke it at `https://myaccount.google.com/permissions`.

Remember the scope is `yt-analytics.readonly`, so nothing can upload, edit, or
delete anything on the channel.

---

## Troubleshooting

| Problem | Cause |
|---|---|
| `invalid_grant` after 7 days | Consent screen is still in Testing mode. Publish the app and get a new refresh token. |
| Claude can't connect | Server not reachable on public HTTPS, or wrong path. Open the URL in a browser first. |
| Empty rows | Data lag. Analytics can be 1-2 days behind, and retention needs up to 2 days to process. |
| `403 forbidden` | The API isn't enabled in the project, or the scope is missing from the token. |
| Numbers differ from Studio | Normal. The monetisation eligibility page validates separately and lags about a week. |

---

## Honest cost/benefit

This saves a few minutes per video. It does not touch the part that decides
whether the channel grows: picking components, writing scenes, judging
generations, choosing thumbnails. Build it because building is enjoyable and
the data becomes easier to compare over time — not because it will move the
numbers.

If the setup starts eating days, stop at level 0 or 1 and keep making videos.
