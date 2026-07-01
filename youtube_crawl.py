import argparse
import asyncio

from app.database import SessionLocal
from app.models import Source
from app.services.scraper_service import crawl_source


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a YouTube source crawl job.")
    parser.add_argument("source_id", type=int)
    parser.add_argument("--max-count", type=int, default=30)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        source = db.get(Source, args.source_id)
        if source is None:
            raise SystemExit(f"Source {args.source_id} not found")
        job = await crawl_source(db, source, max_count=args.max_count)
        print({"job_id": job.id, "status": job.status, "videos_found": job.videos_found, "videos_new": job.videos_new})
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
