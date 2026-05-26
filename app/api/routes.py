import logging
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
import asyncio
from pydantic import BaseModel

from app.credentials.dependencies import get_current_user
from app.crawler.crawler import SemanticCrawler
from app.transformer.llms_generator import generate_llms_txt

logger = logging.getLogger("api.routes")

router = APIRouter()

class CrawlRequest(BaseModel):
    url: str

def get_site_name(url: str) -> str:
    """Derives a clean, readable name from a URL."""
    try:
        clean = url.replace("https://", "").replace("http://", "").replace("www.", "")
        name = clean.split("/")[0].split(".")[0]
        return name.capitalize()
    except Exception:
        return "Website"

@router.post("/crawl-site")
async def crawl_site(request: CrawlRequest, user: dict = Depends(get_current_user)):
    target_url = request.url.strip()
    if not target_url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Must start with http:// or https://")

    logger.info(f"User {user.get('email')} triggered semantic crawl for URL: {target_url}")
    
    async def event_generator():
        msg_queue = asyncio.Queue()

        async def progress_callback(msg: str):
            await msg_queue.put(msg)

        async def run_crawl():
            try:
                crawler = SemanticCrawler()
                crawl_data = await crawler.crawl(target_url, progress_callback=progress_callback)

                if crawl_data.get("status") == "error":
                    await msg_queue.put({"type": "error", "message": crawl_data.get("message", "Crawl failed")})
                    return

                pages = crawl_data.get("pages", [])
                if not pages:
                    await msg_queue.put({"type": "error", "message": "No high-quality readable pages could be extracted."})
                    return

                site_name = get_site_name(target_url)

                # 2. Transform crawled content to standard llms.txt format
                await progress_callback("[TRANSFORMER] Generating llms.txt")
                llms_txt = generate_llms_txt(site_name, pages, target_url)

                # 3. Write outputs to persistence directories
                outputs_dir = Path("outputs")
                outputs_dir.mkdir(exist_ok=True)
                
                llms_txt_path = outputs_dir / "llms.txt"
                llms_txt_path.write_text(llms_txt, encoding="utf-8")
                logger.info("Saved distilled outputs successfully to outputs/llms.txt")

                # 4. Record to user crawl history
                try:
                    history_path = outputs_dir / "history.json"
                    history_records = []
                    if history_path.exists():
                        try:
                            history_records = json.loads(history_path.read_text(encoding="utf-8"))
                        except Exception:
                            history_records = []

                    new_record = {
                        "url": target_url,
                        "title": site_name,
                        "timestamp": datetime.utcnow().isoformat(),
                        "llms_txt": llms_txt,
                        "user": user.get("email", "anonymous")
                    }

                    # Deduplicate history: drop matching URLs for this user
                    history_records = [
                        item for item in history_records 
                        if not (item.get("url") == target_url and item.get("user") == user.get("email"))
                    ]
                    
                    history_records.insert(0, new_record)
                    # Bounded capacity
                    history_records = history_records[:50]
                    
                    history_path.write_text(json.dumps(history_records, indent=2, ensure_ascii=False), encoding="utf-8")
                    logger.info(f"Crawl history record registered for {user.get('email')}")
                except Exception as e:
                    logger.error(f"Failed to record search history: {e}")

                await msg_queue.put({
                    "type": "success",
                    "crawl_method": crawl_data.get("crawl_method", "static"),
                    "total_pages_processed": len(pages),
                    "processed_pages": [
                        {
                            "title": p["title"],
                            "url": p["url"]
                        }
                        for p in pages
                    ]
                })

            except Exception as e:
                logger.error(f"Crawl execution task failed: {e}", exc_info=True)
                await msg_queue.put({"type": "error", "message": str(e)})

        # Run the crawl task in background
        crawl_task = asyncio.create_task(run_crawl())

        while not crawl_task.done() or not msg_queue.empty():
            try:
                msg = await asyncio.wait_for(msg_queue.get(), timeout=0.1)
                if isinstance(msg, dict):
                    yield json.dumps(msg) + "\n"
                else:
                    yield json.dumps({"type": "progress", "message": msg}) + "\n"
                msg_queue.task_done()
            except asyncio.TimeoutError:
                continue

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@router.get("/llms.txt")
async def get_llms_txt(user: dict = Depends(get_current_user)):
    file_path = Path("outputs/llms.txt")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="No generated llms.txt found. Please trigger a crawl first.")
    
    return FileResponse(
        path=str(file_path),
        media_type="text/plain",
        filename="llms.txt"
    )

@router.get("/history")
async def get_history(user: dict = Depends(get_current_user)):
    history_path = Path("outputs/history.json")
    if not history_path.exists():
        return []
    
    try:
        all_records = json.loads(history_path.read_text(encoding="utf-8"))
        # Filter history records by the authenticated user's email
        user_records = [
            item for item in all_records 
            if item.get("user") == user.get("email")
        ]
        return user_records
    except Exception:
        return []
