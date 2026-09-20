import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

port = int(os.environ.get("PORT", 8000))
host = os.environ.get("HOST", "0.0.0.0")

mcp = FastMCP("YouTube Analytics", host=host, port=port)

def api():
    refresh_token = os.environ["REFRESH_TOKEN"]
    client_id = os.environ["CLIENT_ID"]
    client_secret = os.environ["CLIENT_SECRET"]

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
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
    """Totals for one video: views, watch time (mins), average view duration (seconds) and percentage, likes, comments, subscribers gained."""
    return query(
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,comments,subscribersGained",
        filters=f"video=={video_id}",
    )

@mcp.tool()
def traffic_sources(video_id: str) -> dict:
    """Where the views came from (Shorts feed, search, suggested, external, etc.)."""
    return query("views", dimensions="insightTrafficSourceType",
                 filters=f"video=={video_id}", sort="-views")

@mcp.tool()
def search_terms(video_id: str) -> dict:
    """The YouTube search queries that led viewers to this video."""
    return query("views", dimensions="insightTrafficSourceDetail",
                 filters=f"video=={video_id}", sort="-views")

@mcp.tool()
def retention(video_id: str) -> dict:
    """Retention curve: 100 data points of audienceWatchRatio across the video timeline."""
    return query("audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                 filters=f"video=={video_id}", sort="elapsedVideoTimeRatio")

@mcp.tool()
def channel_totals(start_date: str, end_date: str) -> dict:
    """Channel-wide totals between two dates in YYYY-MM-DD format (views, watch time, subscribers gained)."""
    return query("views,estimatedMinutesWatched,subscribersGained",
                 start=start_date, end=end_date)

@mcp.tool()
def top_videos(start_date: str, end_date: str) -> dict:
    """Best performing videos in a date range (YYYY-MM-DD) sorted by views."""
    return query("views,averageViewPercentage", dimensions="video",
                 start=start_date, end=end_date, sort="-views")

if __name__ == "__main__":
    import sys
    transport = "streamable-http" if "--http" in sys.argv else os.environ.get("TRANSPORT", "stdio")
    mcp.run(transport=transport)
