import os
import re
import asyncio
import urllib.parse
import argparse
import logging
from datetime import datetime
from playwright.async_api import async_playwright
from asyncio import Queue

# Global variables
visited_urls = set()
found_files = set()
base_domain = ""
visited_lock = asyncio.Lock()

def setup_logging(log_level="INFO", log_file=None):
    """Setup logging configuration"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create logger
    logger = logging.getLogger("file_scraper")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

def is_valid_url(url):
    return url.startswith("http")

def is_internal_url(url):
    return base_domain in urllib.parse.urlparse(url).netloc

def sanitize_filename(url):
    return re.sub(r'[^\w\-_\.]', '_', url)

async def download_file(page, file_url, output_dir, logger):
    if file_url in found_files:
        logger.debug(f"File already downloaded, skipping: {file_url}")
        return

    filename = sanitize_filename(urllib.parse.urlparse(file_url).path.split("/")[-1]) or "file"
    filepath = os.path.join(output_dir, filename)

    if not os.path.exists(filepath):
        try:
            logger.info(f"Downloading file: {file_url}")
            resp = await page.request.get(file_url)
            content = await resp.body()
            
            with open(filepath, "wb") as f:
                f.write(content)
            
            file_size = len(content)
            found_files.add(file_url)
            logger.info(f"Successfully downloaded: {filename} ({file_size} bytes)")
            
        except Exception as e:
            logger.error(f"Failed to download {file_url}: {e}")
    else:
        logger.debug(f"File already exists, skipping: {filepath}")

async def worker(queue: Queue, file_ext, output_dir, same_domain_only, playwright, worker_id, logger):
    logger.info(f"Worker {worker_id} starting")
    
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    
    urls_processed = 0
    files_downloaded = 0

    try:
        while not queue.empty():
            url = await queue.get()
            urls_processed += 1

            async with visited_lock:
                if url in visited_urls or not is_valid_url(url):
                    logger.debug(f"Worker {worker_id}: Skipping already visited or invalid URL: {url}")
                    queue.task_done()
                    continue
                visited_urls.add(url)

            logger.debug(f"Worker {worker_id}: Processing URL {urls_processed}: {url}")

            try:
                # Direct file download
                if url.lower().endswith(f".{file_ext.lower()}"):
                    logger.debug(f"Worker {worker_id}: Direct file download detected: {url}")
                    await download_file(page, url, output_dir, logger)
                    files_downloaded += 1
                    queue.task_done()
                    continue
                
                logger.info(f"Worker {worker_id}: Visiting page: {url}")
                
                # Check for download URLs with matching extensions
                if any(param in url.lower() for param in ['download', 'wpdmdl', 'file']):
                    if (f".{file_ext.lower()}" in url.lower() or 
                        any(indicator in url.lower() for indicator in [f'{file_ext}', 'attachment', 'export'])):
                        logger.info(f"Worker {worker_id}: Detected download URL with matching extension: {url}")
                        await download_file(page, url, output_dir, logger)
                        files_downloaded += 1
                        queue.task_done()
                        continue
                    else:
                        logger.debug(f"Worker {worker_id}: Skipping download URL (no matching extension): {url}")
                        queue.task_done()
                        continue
                
                # Navigate to page and extract links
                await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(500)

                links = await page.eval_on_selector_all("a", "els => els.map(el => el.href)")
                new_links_added = 0
                
                for link in links:
                    if not is_valid_url(link):
                        continue
                    if same_domain_only and not is_internal_url(link):
                        logger.debug(f"Worker {worker_id}: Skipping external link: {link}")
                        continue
                    if link.lower().endswith(f".{file_ext.lower()}"):
                        logger.debug(f"Worker {worker_id}: Found target file link: {link}")
                        await download_file(page, link, output_dir, logger)
                        files_downloaded += 1
                    elif link not in visited_urls:
                        await queue.put(link)
                        new_links_added += 1
                        logger.debug(f"Worker {worker_id}: Added new link to queue: {link}")

                logger.info(f"Worker {worker_id}: Extracted {len(links)} links, added {new_links_added} new links to queue")

            except Exception as e:
                # Handle ERR_ABORTED for potential download URLs
                if ("ERR_ABORTED" in str(e) and 
                    any(param in url.lower() for param in ['download', 'wpdmdl', 'file']) and
                    (f".{file_ext.lower()}" in url.lower() or f'{file_ext}' in url.lower())):
                    logger.warning(f"Worker {worker_id}: Navigation failed, trying direct download: {url}")
                    try:
                        await download_file(page, url, output_dir, logger)
                        files_downloaded += 1
                    except Exception as download_error:
                        logger.error(f"Worker {worker_id}: Direct download also failed for {url}: {download_error}")
                else:
                    logger.error(f"Worker {worker_id}: Error visiting {url}: {e}")
            
            queue.task_done()

    except Exception as e:
        logger.error(f"Worker {worker_id}: Unexpected error: {e}")
    finally:
        await browser.close()
        logger.info(f"Worker {worker_id} finished. Processed {urls_processed} URLs, downloaded {files_downloaded} files")

async def main(args):
    global base_domain
    
    # Setup logging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"file_scraper_{timestamp}.log" if args.log_file else None
    logger = setup_logging(args.log_level, log_file)
    
    logger.info("=" * 60)
    logger.info("File Scraper Starting")
    logger.info("=" * 60)
    logger.info(f"Start URL: {args.start_url}")
    logger.info(f"Target extension: {args.ext}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Same domain only: {args.same_domain_only}")
    logger.info(f"Worker threads: {args.threads}")
    logger.info(f"Log level: {args.log_level}")
    if log_file:
        logger.info(f"Log file: {log_file}")
    
    base_domain = urllib.parse.urlparse(args.start_url).netloc
    logger.info(f"Base domain: {base_domain}")
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    logger.info(f"Created/verified output directory: {args.output_dir}")

    queue = asyncio.Queue()
    await queue.put(args.start_url)
    logger.info("Added start URL to queue")

    start_time = datetime.now()
    
    async with async_playwright() as playwright:
        logger.info(f"Starting {args.threads} worker threads")
        tasks = [
            asyncio.create_task(worker(queue, args.ext, args.output_dir, args.same_domain_only, playwright, i+1, logger))
            for i in range(args.threads)
        ]

        await queue.join()
        logger.info("Queue processing completed, cancelling workers")
        
        for t in tasks:
            t.cancel()

    end_time = datetime.now()
    duration = end_time - start_time
    
    logger.info("=" * 60)
    logger.info("File Scraper Completed")
    logger.info("=" * 60)
    logger.info(f"Total URLs visited: {len(visited_urls)}")
    logger.info(f"Total files downloaded: {len(found_files)}")
    logger.info(f"Duration: {duration}")
    logger.info(f"Files saved to: {args.output_dir}")
    
    print(f"\nDone! Downloaded {len(found_files)} .{args.ext} file(s) in {duration}")
    print(f"Check log file for details: {log_file}" if log_file else "")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast async file scraper using Playwright.")
    parser.add_argument("--start-url", required=True, help="Starting URL")
    parser.add_argument("--ext", default="pdf", help="File extension to search (e.g. pdf, csv)")
    parser.add_argument("--output-dir", default="downloads", help="Where to save files")
    parser.add_argument("--same-domain-only", action="store_true", help="Only crawl same domain")
    parser.add_argument("--threads", type=int, default=4, help="Concurrent workers")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Logging level")
    parser.add_argument("--log-file", action="store_true", help="Enable file logging")
    args = parser.parse_args()

    asyncio.run(main(args))