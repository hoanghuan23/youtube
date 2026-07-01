from typing import Any
from urllib.parse import urlparse, parse_qs, unquote

from yt_dlp import YoutubeDL


def extract_keyword_from_youtube_search_url(search_url: str) -> str:
    parsed_url = urlparse(search_url)
    query_params = parse_qs(parsed_url.query)

    keyword = query_params.get("search_query", [""])[0]
    return unquote(keyword).strip()


def normalize_video_url(item: dict[str, Any]) -> str | None:
    video_url = item.get("url") or item.get("webpage_url")
    video_id = item.get("id")

    if video_url and str(video_url).startswith("http"):
        return video_url

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    if video_url:
        return f"https://www.youtube.com/watch?v={video_url}"

    return None


def extract_youtube_video_info(video_url: str) -> dict[str, Any]:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "no_warnings": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    return {
        "video_id": info.get("id"),
        "url": info.get("webpage_url"),
        "title": info.get("title"),
        "description": info.get("description"),
        "channel_name": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "timestamp": info.get("timestamp"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "thumbnail": info.get("thumbnail"),
        "tags": info.get("tags"),
        "categories": info.get("categories"),
        "live_status": info.get("live_status"),
    }


def search_youtube_keyword(keyword_or_url: str, limit: int = 15) -> list[dict[str, Any]]:
    if "youtube.com/results" in keyword_or_url:
        keyword = extract_keyword_from_youtube_search_url(keyword_or_url)
    else:
        keyword = keyword_or_url.strip()

    if not keyword:
        raise ValueError("Không tìm thấy keyword để search")

    search_query = f"ytsearch{limit}:{keyword}"

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "no_warnings": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        search_info = ydl.extract_info(search_query, download=False)

    entries = (search_info or {}).get("entries") or []

    videos = []

    for item in entries:
        if not item:
            continue

        video_url = normalize_video_url(item)

        if not video_url:
            continue

        try:
            video_data = extract_youtube_video_info(video_url)
            videos.append(video_data)
        except Exception as exc:
            videos.append({
                "video_id": item.get("id"),
                "url": video_url,
                "error": str(exc),
            })

        if len(videos) >= limit:
            break

    return videos


if __name__ == "__main__":
    # Cách 1: truyền URL search YouTube
    # url = "https://www.youtube.com/results?search_query=s%C6%A1n+t%C3%B9ng"

    # Cách 2: truyền trực tiếp keyword
    url = "world cup"

    videos = search_youtube_keyword(url, limit=15)

    for index, video in enumerate(videos, start=1):
        print(f"\n===== VIDEO {index} =====")
        for key, value in video.items():
            print(f"{key}: {value}")