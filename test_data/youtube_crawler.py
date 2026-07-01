from yt_dlp import YoutubeDL
from datetime import datetime, timezone
from typing import Any


def format_upload_date(upload_date: str | None) -> str | None:
    """Convert YYYYMMDD -> YYYY-MM-DD."""
    if not upload_date:
        return None
    try:
        return datetime.strptime(upload_date, "%Y%m%d").date().isoformat()
    except ValueError:
        return upload_date


def extract_youtube_video_info(video_url: str) -> dict[str, Any]:
    """Extract detail info for one YouTube video/short URL."""
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "no_warnings": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    timestamp = info.get("timestamp")

    return {
        "video_id": info.get("id"),
        "url": info.get("webpage_url") or video_url,
        "title": info.get("title"),
        "description": info.get("description"),
        "channel_name": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url"),
        "uploader": info.get("uploader"),
        "uploader_id": info.get("uploader_id"),
        "upload_date": format_upload_date(info.get("upload_date")),
        "timestamp": timestamp,
        "created_at_utc": (
            datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            if timestamp
            else None
        ),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "thumbnail": info.get("thumbnail"),
        "tags": info.get("tags"),
        "categories": info.get("categories"),
    }


def extract_youtube_shorts(channel_shorts_url: str, limit: int = 15) -> list[dict[str, Any]]:
    """
    Extract latest shorts from a YouTube channel shorts tab.

    Example URL:
        https://www.youtube.com/@Sontungmtp/shorts
    """
    playlist_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,          # lấy danh sách URL trước, chưa lấy full metric
        "playlistend": limit,          # chỉ lấy N video đầu tiên
        "ignoreerrors": True,
        # "no_warnings": True,
    }

    with YoutubeDL(playlist_opts) as ydl:
        playlist_info = ydl.extract_info(channel_shorts_url, download=False)

    entries = playlist_info.get("entries") or []
    videos: list[dict[str, Any]] = []

    for item in entries[:limit]:
        if not item:
            continue

        video_url = item.get("url") or item.get("webpage_url")
        video_id = item.get("id")

        # Khi extract_flat=True, url đôi khi chỉ là video_id
        if video_url and not str(video_url).startswith("http"):
            video_url = f"https://www.youtube.com/watch?v={video_url}"
        elif not video_url and video_id:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

        if not video_url:
            continue

        try:
            videos.append(extract_youtube_video_info(video_url))
        except Exception as exc:
            videos.append({
                "video_id": video_id,
                "url": video_url,
                "error": str(exc),
            })

    return videos


if __name__ == "__main__":
    # url = "https://www.youtube.com/@Sontungmtp/videos" #video dài
    url = "https://www.youtube.com/@vtv24/shorts"  # video shorts

    shorts = extract_youtube_shorts(url, limit=5)

    print(f"Total shorts: {len(shorts)}")
    for index, video in enumerate(shorts, start=1):
        print("-" * 80)
        print(f"#{index}")
        for key, value in video.items():
            print(f"{key}: {value}")
