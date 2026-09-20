import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

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

def get_video_metadata(video_ids: list):
    """Fetch titles, publish dates, and privacy status for a list of video IDs (batched up to 50)."""
    if not video_ids:
        return {}
    
    metadata = {}
    yt_data = api_data()
    # Batch IDs in chunks of 50
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        try:
            res = yt_data.videos().list(part="snippet,status", id=",".join(chunk)).execute()
            for item in res.get("items", []):
                v_id = item["id"]
                snippet = item.get("snippet", {})
                status = item.get("status", {})
                metadata[v_id] = {
                    "title": snippet.get("title", "Unknown Title"),
                    "publishedAt": snippet.get("publishedAt", ""),
                    "privacyStatus": status.get("privacyStatus", "unknown")
                }
        except Exception as e:
            # Fallback if Data API fails or scope not granted yet
            print(f"[Warning] Failed to fetch metadata: {e}")
            break
            
    return metadata

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
    """Totals for one video including title, publish date, views, watch time (mins), average view duration and percentage, likes, comments, subscribers gained."""
    analytics = query(
        "views,estimatedMinutesWatched,averageViewDuration,"
        "averageViewPercentage,likes,comments,subscribersGained",
        filters=f"video=={video_id}",
    )
    meta = get_video_metadata([video_id]).get(video_id, {})
    return {
        "video_id": video_id,
        "title": meta.get("title", "Unknown Title"),
        "publishedAt": meta.get("publishedAt", ""),
        "privacyStatus": meta.get("privacyStatus", "unknown"),
        "headers": analytics.get("headers", []),
        "stats": analytics.get("rows", [[]])[0] if analytics.get("rows") else []
    }

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
def channel_totals(start_date: str = "2020-01-01", end_date: str = "2035-01-01") -> dict:
    """Channel-wide totals between two dates in YYYY-MM-DD format (views, watch time, subscribers gained)."""
    return query("views,estimatedMinutesWatched,subscribersGained",
                 start=start_date, end=end_date)

@mcp.tool()
def list_channel_videos(public_only: bool = True, max_results: int = 200) -> dict:
    """List videos in the channel with titles, publish dates, privacy status, and performance metrics (views, watch time, avg view %, likes, subs gained). By default filters for public videos only."""
    res = query("views,estimatedMinutesWatched,averageViewPercentage,likes,subscribersGained",
                dimensions="video", sort="-views", max_results=max_results)
    
    video_ids = [row[0] for row in res.get("rows", [])]
    meta = get_video_metadata(video_ids)
    
    enriched_rows = []
    headers = ["video_id", "title", "publishedAt", "privacyStatus", "views", "estimatedMinutesWatched", "averageViewPercentage", "likes", "subscribersGained"]
    
    for row in res.get("rows", []):
        vid = row[0]
        v_meta = meta.get(vid, {"title": "Unknown", "publishedAt": "", "privacyStatus": "unknown"})
        
        if public_only and v_meta.get("privacyStatus") not in ("public", "unknown"):
            continue
            
        enriched_rows.append([
            vid,
            v_meta.get("title"),
            v_meta.get("publishedAt"),
            v_meta.get("privacyStatus"),
            *row[1:]
        ])
        
    return {"headers": headers, "rows": enriched_rows}

@mcp.tool()
def top_videos(start_date: str = "2020-01-01", end_date: str = "2035-01-01", public_only: bool = True, max_results: int = 200) -> dict:
    """Best performing videos in a date range (YYYY-MM-DD) sorted by views with titles and publish dates."""
    res = query("views,estimatedMinutesWatched,averageViewPercentage,likes,subscribersGained",
                dimensions="video",
                start=start_date, end=end_date, sort="-views", max_results=max_results)
    
    video_ids = [row[0] for row in res.get("rows", [])]
    meta = get_video_metadata(video_ids)
    
    enriched_rows = []
    headers = ["video_id", "title", "publishedAt", "privacyStatus", "views", "estimatedMinutesWatched", "averageViewPercentage", "likes", "subscribersGained"]
    
    for row in res.get("rows", []):
        vid = row[0]
        v_meta = meta.get(vid, {"title": "Unknown", "publishedAt": "", "privacyStatus": "unknown"})
        
        if public_only and v_meta.get("privacyStatus") not in ("public", "unknown"):
            continue
            
        enriched_rows.append([
            vid,
            v_meta.get("title"),
            v_meta.get("publishedAt"),
            v_meta.get("privacyStatus"),
            *row[1:]
        ])
        
    return {"headers": headers, "rows": enriched_rows}

if __name__ == "__main__":
    import sys
    transport = "streamable-http" if "--http" in sys.argv else os.environ.get("TRANSPORT", "stdio")
    mcp.run(transport=transport)
