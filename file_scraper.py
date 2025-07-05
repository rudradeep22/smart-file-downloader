import os
import re
import asyncio
import urllib.parse
import argparse
from playwright.async_api import async_playwright
from asyncio import Queue

visited_urls = set()
found_files = set()
base_domain = ""

def is_valid_url(url):
    return url.startswith("http")

def is_internal_url(url):
    return base_domain in urllib.parse.urlparse(url).netloc

def sanitize_filename(url):
    return re.sub(r'[^\w\-_\.]', '_', url)

async def download_file(page, file_url, output_dir):
    if file_url in found_files:
        return

    filename = sanitize_filename(urllib.parse.urlparse(file_url).path.split("/")[-1]) or "file"
    filepath = os.path.join(output_dir, filename)

    if not os.path.exists(filepath):
        try:
            print(f"Downloading: {file_url}")
            resp = await page.request.get(file_url)
            content = await resp.body()
            with open(filepath, "wb") as f:
                f.write(content)
            found_files.add(file_url)
        except Exception as e:
            print(f"Failed to download {file_url}: {e}")

async def worker(queue: Queue, file_ext, output_dir, same_domain_only, playwright):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    while not queue.empty():
        url = await queue.get()

        if url in visited_urls or not is_valid_url(url):
            queue.task_done()
            continue

        visited_urls.add(url)

        try:
            if url.lower().endswith(f".{file_ext.lower()}"):
                await download_file(page, url, output_dir)
                queue.task_done()
                continue
            
            print(f"Visiting: {url}")
            
            # Only try direct download if URL looks like download AND has matching extension
            if any(param in url.lower() for param in ['download', 'wpdmdl', 'file']):
                if (f".{file_ext.lower()}" in url.lower() or 
                    any(indicator in url.lower() for indicator in [f'{file_ext}', 'attachment', 'export'])):
                    print(f"Detected download URL with matching extension, attempting direct download: {url}")
                    await download_file(page, url, output_dir)
                    queue.task_done()
                    continue
                else:
                    # Skip download URLs that don't match our target extension
                    print(f"Skipping download URL (no matching extension): {url}")
                    queue.task_done()
                    continue
            
            await page.goto(url, timeout=30000, wait_until='domcontentloaded')
            await page.wait_for_timeout(500)

            links = await page.eval_on_selector_all("a", "els => els.map(el => el.href)")
            for link in links:
                if not is_valid_url(link):
                    continue
                if same_domain_only and not is_internal_url(link):
                    continue
                if link.lower().endswith(f".{file_ext.lower()}"):
                    await download_file(page, link, output_dir)
                elif link not in visited_urls:
                    await queue.put(link)

        except Exception as e:
            # Only handle ERR_ABORTED for URLs that might have our target extension
            if ("ERR_ABORTED" in str(e) and 
                any(param in url.lower() for param in ['download', 'wpdmdl', 'file']) and
                (f".{file_ext.lower()}" in url.lower() or f'{file_ext}' in url.lower())):
                print(f"Navigation failed but trying direct download for matching extension: {url}")
                try:
                    await download_file(page, url, output_dir)
                except Exception as download_error:
                    print(f"Direct download also failed for {url}: {download_error}")
            else:
                print(f"Error visiting {url}: {e}")
        queue.task_done()

    await browser.close()

async def main(args):
    global base_domain
    base_domain = urllib.parse.urlparse(args.start_url).netloc
    os.makedirs(args.output_dir, exist_ok=True)

    queue = asyncio.Queue()
    await queue.put(args.start_url)

    async with async_playwright() as playwright:
        tasks = [
            asyncio.create_task(worker(queue, args.ext, args.output_dir, args.same_domain_only, playwright))
            for _ in range(args.threads)
        ]

        await queue.join()
        for t in tasks:
            t.cancel()

        print(f"\n Done! Downloaded {len(found_files)} .{args.ext} file(s).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast async file scraper using Playwright.")
    parser.add_argument("--start-url", required=True, help="Starting URL")
    parser.add_argument("--ext", default="pdf", help="File extension to search (e.g. pdf, csv)")
    parser.add_argument("--output-dir", default="downloads", help="Where to save files")
    parser.add_argument("--same-domain-only", action="store_true", help="Only crawl same domain")
    parser.add_argument("--threads", type=int, default=4, help="Concurrent workers")
    args = parser.parse_args()

    asyncio.run(main(args))
