import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Load latest tokens directly from .env
load_dotenv(override=True)

port = int(os.environ.get("PORT", 8000))
host = os.environ.get("HOST", "0.0.0.0")

mcp = FastMCP("YouTube Analytics", host=host, port=port)

def get_creds():
    refresh_token = os.environ["REFRESH_TOKEN"]
    client_id = os.environ["CLIENT_ID"]
    client_secret = os.environ["CLIENT_SECRET"]

    return Credentials(
        None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )

def api_analytics():
    return build("youtubeAnalytics", "v2", credentials=get_creds())

def api_data():
    return build("youtube", "v3", credentials=get_creds())

def get_all_channel_uploads(public_only=True):
    """Fetches all uploaded videos directly from the channel's uploads playlist in real time."""
    yt_data = api_data()
    ch = yt_data.channels().list(mine=True, part="contentDetails").execute()
    if not ch.get("items"):
        return []
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = []
    page_token = None
    while True:
        pl = yt_data.playlistItems().list(
            playlistId=uploads_id,
            part="snippet,status",
            maxResults=50,
            pageToken=page_token
        ).execute()
        items.extend(pl.get("items", []))
        page_token = pl.get("nextPageToken")
        if not page_token or len(items) >= 150:
            break

    video_ids = [it["snippet"]["resourceId"]["videoId"] for it in items]
    
    # Batch fetch full metadata and live statistics (views, likes, comments)
    video_details = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        res = yt_data.videos().list(part="snippet,status,statistics", id=",".join(chunk)).execute()
        for v in res.get("items", []):
            privacy = v["status"].get("privacyStatus", "unknown")
            if public_only and privacy != "public":
                continue
            video_details.append({
                "video_id": v["id"],
                "title": v["snippet"].get("title", "Unknown Title"),
                "publishedAt": v["snippet"].get("publishedAt", ""),
                "privacyStatus": privacy,
                "viewCount": int(v.get("statistics", {}).get("viewCount", 0)),
                "likeCount": int(v.get("statistics", {}).get("likeCount", 0)),
                "commentCount": int(v.get("statistics", {}).get("commentCount", 0)),
            })
    return video_details

def query(metrics, dimensions=None, filters=None, sort=None,
          start="2020-01-01", end="2035-01-01", max_results=None):
    kwargs = dict(ids="channel==MINE", startDate=start, endDate=end,
                  metrics=metrics)
    if dimensions: kwargs["dimensions"] = dimensions
    if filters:    kwargs["filters"] = filters
    if sort:       kwargs["sort"] = sort
    if max_results: kwargs["maxResults"] = max_results
    r = api_analytics().reports().query(**kwargs).execute()
    headers = [h["name"] for h in r.get("columnHeaders", [])]
    return {"headers": headers, "rows": r.get("rows", [])}

@mcp.tool()
def video_stats(video_id: str) -> dict:
    """Totals for one video including real-time title, publish date, views, watch time (mins), average view duration and percentage, likes, comments, subscribers gained."""
    analytics = query(
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,comments,subscribersGained",
        filters=f"video=={video_id}",
    )
    
    yt_data = api_data()
    v_res = yt_data.videos().list(part="snippet,status,statistics", id=video_id).execute()
    v_item = v_res.get("items", [{}])[0] if v_res.get("items") else {}
    snippet = v_item.get("snippet", {})
    status = v_item.get("status", {})
    stats = v_item.get("statistics", {})

    return {
        "video_id": video_id,
        "title": snippet.get("title", "Unknown Title"),
        "publishedAt": snippet.get("publishedAt", ""),
        "privacyStatus": status.get("privacyStatus", "unknown"),
        "liveViews": int(stats.get("viewCount", 0)),
        "liveLikes": int(stats.get("likeCount", 0)),
        "liveComments": int(stats.get("commentCount", 0)),
        "analyticsHeaders": analytics.get("headers", []),
        "analyticsStats": analytics.get("rows", [[]])[0] if analytics.get("rows") else []
    }

@mcp.tool()
def traffic_sources(video_id: str) -> dict:
    """Where the views came from (Shorts feed, search, suggested, external, etc.)."""
    return query("views", dimensions="insightTrafficSourceType",
                 filters=f"video=={video_id}", sort="-views")

@mcp.tool()
def search_terms(video_id: str, max_results: int = 25) -> dict:
    """The YouTube search queries that led viewers to this video."""
    return query("views", dimensions="insightTrafficSourceDetail",
                 filters=f"video=={video_id};insightTrafficSourceType==YT_SEARCH",
                 sort="-views", max_results=max_results)

@mcp.tool()
def retention(video_id: str) -> dict:
    """Retention curve: 100 data points of audienceWatchRatio across the video timeline."""
    return query("audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                 filters=f"video=={video_id}", sort="elapsedVideoTimeRatio")

@mcp.tool()
def channel_totals(start_date: str = "2020-01-01", end_date: str = "2035-01-01") -> dict:
    """Channel-wide totals between two dates in YYYY-MM-DD format (views, watch time, subscribers gained)."""
    return query("views,estimatedMinutesWatched,subscribersGained",
                 start=start_date, end=end_date)

@mcp.tool()
def list_channel_videos(public_only: bool = True, max_results: int = 50) -> dict:
    """List all videos/shorts in the channel fetched directly from YouTube with titles, publish dates, privacy status, live views, likes, and analytics."""
    uploads = get_all_channel_uploads(public_only=public_only)
    
    # Query analytics for all videos
    analytics_map = {}
    try:
        res = query("views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
                    dimensions="video", sort="-views", max_results=200)
        for row in res.get("rows", []):
            analytics_map[row[0]] = {
                "analyticsViews": row[1],
                "watchMinutes": row[2],
                "avgViewPercentage": row[3],
                "subsGained": row[4]
            }
    except Exception as e:
        print(f"[Warning] Analytics query error: {e}")

    rows = []
    headers = ["video_id", "title", "publishedAt", "privacyStatus", "liveViews", "liveLikes", "avgViewPercentage", "subsGained", "watchMinutes"]
    
    for v in uploads[:max_results]:
        vid = v["video_id"]
        ana = analytics_map.get(vid, {})
        rows.append([
            vid,
            v["title"],
            v["publishedAt"][:10],
            v["privacyStatus"],
            v["viewCount"],
            v["likeCount"],
            ana.get("avgViewPercentage", 0),
            ana.get("subsGained", 0),
            ana.get("watchMinutes", 0)
        ])
        
    return {"headers": headers, "rows": rows}

@mcp.tool()
def top_videos(start_date: str = "2020-01-01", end_date: str = "2035-01-01", public_only: bool = True, max_results: int = 50) -> dict:
    """Best performing videos in the channel sorted by live views with titles, publish dates, and retention."""
    return list_channel_videos(public_only=public_only, max_results=max_results)

if __name__ == "__main__":
    import sys
    transport = "streamable-http" if "--http" in sys.argv else os.environ.get("TRANSPORT", "stdio")
    mcp.run(transport=transport)
