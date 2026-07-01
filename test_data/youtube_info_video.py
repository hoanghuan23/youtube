from yt_dlp import YoutubeDL


def extract_youtube_video_info(video_url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "no_warnings": True
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    video_data = {
        "video_id": info.get("id"),
        "url": info.get("webpage_url"),
        "title": info.get("title"),
        "description": info.get("description"),
        "channel_name": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),  # dạng YYYYMMDD
        "timestamp": info.get("timestamp"),      # Unix timestamp nếu có
        "duration": info.get("duration"),        # giây
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "thumbnail": info.get("thumbnail"),
        "tags": info.get("tags"),
        "categories": info.get("categories"),
        "live_status": info.get("live_status"),
    }

    return video_data


if __name__ == "__main__":
    # url = "https://www.youtube.com/watch?v=iYlODtkyw_I"
    url = "https://www.youtube.com/shorts/YASe05eAlBI"

    data = extract_youtube_video_info(url)

    for key, value in data.items():
        print(f"{key}: {value}")