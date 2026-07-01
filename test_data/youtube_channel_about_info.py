from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from yt_dlp import YoutubeDL


def compact_count_to_int(value: str | int | None) -> int | None:
    """
    Convert count text sang int.

    Thực tế:
    - "4,6 Tr người đăng ký" -> 4600000
    - "753 video" -> 753
    - "1.159.517.791 lượt xem" -> 1159517791
    - "4.6M subscribers" -> 4600000
    """
    if value is None:
        return None

    if isinstance(value, int):
        return value

    text = str(value).strip()
    if not text:
        return None

    lower = text.lower()

    match = re.search(r"\d[\d.,]*", text)
    if not match:
        return None

    number_text = match.group(0)
    suffix_text = lower[match.end() :]

    multiplier = 1
    if (
        any(x in lower for x in ["billion"])
        or re.match(r"\s*(?:tỷ|tỉ|b)\b", suffix_text)
    ):
        multiplier = 1_000_000_000
    elif (
        any(x in lower for x in ["triệu", "million"])
        or re.match(r"\s*(?:tr|m)\b", suffix_text)
    ):
        multiplier = 1_000_000
    elif (
        any(x in lower for x in ["nghìn", "nghin", "thousand"])
        or re.match(r"\s*(?:n|k)\b", suffix_text)
    ):
        multiplier = 1_000

    if multiplier == 1:
        digits = re.sub(r"\D", "", number_text)
        return int(digits) if digits else None

    number_text = number_text.replace(",", ".")
    try:
        return int(float(number_text) * multiplier)
    except ValueError:
        return None


def get_text_runs(data: Any) -> list[str]:
    """
    Duyệt JSON ytInitialData để lấy các đoạn text hiển thị.
    Dùng để tìm các text như:
    - "4,6 Tr người đăng ký"
    - "753 video"
    - "1.159.517.791 lượt xem"
    """
    results: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            simple_text = obj.get("simpleText")
            if isinstance(simple_text, str):
                results.append(simple_text)

            text = obj.get("text")
            if isinstance(text, dict) and isinstance(text.get("content"), str):
                results.append(text["content"])

            runs = obj.get("runs")
            if isinstance(runs, list):
                parts = []
                for run in runs:
                    if isinstance(run, dict) and isinstance(run.get("text"), str):
                        parts.append(run["text"])
                if parts:
                    results.append("".join(parts))

            for value in obj.values():
                walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return results


def find_about_channel_view_model(data: Any) -> dict[str, Any] | None:
    """
    YouTube desktop mới đặt số liệu chính trong aboutChannelViewModel.
    Ưu tiên node này để không bắt nhầm channel/video gợi ý trong trang.
    """

    def walk(obj: Any) -> dict[str, Any] | None:
        if isinstance(obj, dict):
            view_model = obj.get("aboutChannelViewModel")
            if isinstance(view_model, dict):
                return view_model

            for value in obj.values():
                found = walk(value)
                if found:
                    return found

        elif isinstance(obj, list):
            for item in obj:
                found = walk(item)
                if found:
                    return found

        return None

    return walk(data)


def extract_yt_initial_data(html: str) -> dict[str, Any] | None:
    """
    Lấy JSON ytInitialData từ HTML YouTube.
    """
    patterns = [
        r"var ytInitialData\s*=\s*({.*?});</script>",
        r"window\[['\"]ytInitialData['\"]\]\s*=\s*({.*?});",
        r"ytInitialData\s*=\s*({.*?});",
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.DOTALL)
        if not match:
            continue

        raw_json = match.group(1)
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            continue

    return None


def normalize_channel_about_url(channel_url: str) -> str:
    """
    Chuẩn hóa URL về tab /about để lấy số subscriber, video, views.
    """
    url = channel_url.strip().rstrip("/")

    # Nếu đang là /videos hoặc /shorts thì đổi sang /about
    url = re.sub(r"/(videos|shorts|featured|streams|playlists|community)$", "", url)

    return f"{url}/about"


def find_first_count(texts: list[str], keywords: list[str]) -> int | None:
    for text in texts:
        lower = text.lower()
        if any(keyword in lower for keyword in keywords):
            value = compact_count_to_int(text)
            if value is not None:
                return value
    return None


def extract_channel_id_from_html_or_info(html: str, info: dict[str, Any]) -> str | None:
    for key in ["channel_id", "uploader_id", "id"]:
        value = info.get(key)
        if isinstance(value, str) and value.startswith("UC"):
            return value

    patterns = [
        r'"channelId":"(UC[^"]+)"',
        r'"browseId":"(UC[^"]+)"',
        r'"externalId":"(UC[^"]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)

    return None


def extract_handle(channel_url: str, info: dict[str, Any], texts: list[str]) -> str | None:
    # Ưu tiên từ URL
    match = re.search(r"youtube\.com/(@[^/?#]+)", channel_url)
    if match:
        return match.group(1)

    # Sau đó từ yt-dlp
    for key in ["uploader_id", "channel"]:
        value = info.get(key)
        if isinstance(value, str) and value.startswith("@"):
            return value

    # Cuối cùng tìm trong text runs
    for text in texts:
        text = text.strip()
        if text.startswith("@"):
            return text.split()[0]

    return None


def get_best_thumbnail(info: dict[str, Any]) -> str | None:
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        return thumbnails[-1].get("url")

    return info.get("thumbnail")


def extract_channel_info(channel_url: str) -> dict[str, Any]:
    """
    Lấy thông tin channel YouTube giống popup About:
    - url
    - video_count
    - view_count
    - channel_handle
    - channel_title
    - subscriber_count
    - thumbnail_url
    - youtube_channel_id

    Cách làm:
    1. Dùng yt-dlp lấy metadata cơ bản.
    2. Tải HTML trang /about.
    3. Parse ytInitialData để lấy subscriber_count, video_count, view_count.
    """

    about_url = normalize_channel_about_url(channel_url)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": 1,
        "ignoreerrors": True,
        "no_warnings": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(about_url, download=False)
        html = ydl.urlopen(about_url).read().decode("utf-8", errors="ignore")

    initial_data = extract_yt_initial_data(html)
    texts = get_text_runs(initial_data) if initial_data else []
    about_view_model = find_about_channel_view_model(initial_data) if initial_data else None

    subscriber_count = None
    video_count = None
    view_count = None

    if about_view_model:
        subscriber_count = compact_count_to_int(about_view_model.get("subscriberCountText"))
        video_count = compact_count_to_int(about_view_model.get("videoCountText"))
        view_count = compact_count_to_int(about_view_model.get("viewCountText"))

    if subscriber_count is None:
        subscriber_count = find_first_count(
            texts,
            ["người đăng ký", "subscriber", "subscribers"],
        )

    if video_count is None:
        video_count = find_first_count(
            texts,
            [" video", "videos"],
        )

    if view_count is None:
        view_count = find_first_count(
            texts,
            ["lượt xem", "views"],
        )

    channel_title = (
        info.get("channel")
        or info.get("uploader")
        or info.get("title")
        or info.get("playlist_title")
    )

    channel_handle = extract_handle(channel_url, info, texts)
    youtube_channel_id = (
        about_view_model.get("channelId")
        if about_view_model and isinstance(about_view_model.get("channelId"), str)
        else extract_channel_id_from_html_or_info(html, info)
    )
    thumbnail_url = get_best_thumbnail(info)

    canonical_url = (
        (about_view_model.get("canonicalChannelUrl") if about_view_model else None)
        or info.get("channel_url")
        or info.get("uploader_url")
        or (f"https://www.youtube.com/{channel_handle}" if channel_handle else channel_url)
    )

    return {
        "url": canonical_url,
        "video_count": video_count,
        "view_count": view_count,
        "channel_handle": channel_handle,
        "channel_title": channel_title,
        "subscriber_count": subscriber_count,
        "thumbnail_url": thumbnail_url,
        "youtube_channel_id": youtube_channel_id,
    }


if __name__ == "__main__":
    url = "https://www.youtube.com/@vtv24"

    channel = extract_channel_info(url)

    for key, value in channel.items():
        print(f"{key}: {value}")
