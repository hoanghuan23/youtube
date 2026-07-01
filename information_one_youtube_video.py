import argparse
import asyncio

from app.services.youtube_client import YouTubeClient


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect one YouTube video through the client interface.")
    parser.add_argument("youtube_url")
    args = parser.parse_args()

    item = await YouTubeClient().get_video_info(args.youtube_url)
    print(item)


if __name__ == "__main__":
    asyncio.run(main())
