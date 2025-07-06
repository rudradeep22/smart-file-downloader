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
credential_cache = {}  # Store credentials by domain

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
        file_handler.setLevel(logging.DEBUG)  
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

async def identify_form_fields(page):
    """Identify common form fields and return a mapping of field types to their selectors"""
    field_types = {
        "username": [],
        "email": [],
        "password": [],
        "submit": []
    }
    
    # Find username/email fields
    username_selectors = await page.evaluate("""() => {
        const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="email"], input:not([type])'));
        return inputs.filter(el => {
            const name = el.name ? el.name.toLowerCase() : '';
            const id = el.id ? el.id.toLowerCase() : '';
            const placeholder = el.placeholder ? el.placeholder.toLowerCase() : '';
            return name.includes('user') || name.includes('email') || name.includes('login') || 
                   id.includes('user') || id.includes('email') || id.includes('login') ||
                   placeholder.includes('user') || placeholder.includes('email') || placeholder.includes('login');
        }).map(el => {
            return {
                selector: el.id ? `#${el.id}` : (el.name ? `[name="${el.name}"]` : null),
                name: el.name || '',
                placeholder: el.placeholder || ''
            };
        }).filter(item => item.selector);
    }""")
    
    # Find password fields
    password_selectors = await page.evaluate("""() => {
        const inputs = Array.from(document.querySelectorAll('input[type="password"]'));
        return inputs.map(el => {
            return {
                selector: el.id ? `#${el.id}` : (el.name ? `[name="${el.name}"]` : null),
                name: el.name || '',
                placeholder: el.placeholder || ''
            };
        }).filter(item => item.selector);
    }""")
    
    # Find submit buttons
    submit_selectors = await page.evaluate("""() => {
        const buttons = Array.from(document.querySelectorAll('input[type="submit"], button[type="submit"], button'));
        return buttons.filter(el => {
            const text = el.innerText ? el.innerText.toLowerCase() : '';
            return text.includes('login') || text.includes('sign in') || text.includes('submit') || 
                   el.type === 'submit';
        }).map(el => {
            return {
                selector: el.id ? `#${el.id}` : (el.name ? `[name="${el.name}"]` : null),
                text: el.innerText || ''
            };
        }).filter(item => item.selector);
    }""")
    
    field_types["username"] = username_selectors
    field_types["password"] = password_selectors
    field_types["submit"] = submit_selectors
    
    return field_types

async def has_login_form(page):
    """Check if the page likely contains a login form"""
    form_count = await page.evaluate("document.querySelectorAll('form').length")
    if form_count == 0:
        return False
    
    password_fields = await page.evaluate("document.querySelectorAll('input[type=\"password\"]').length")
    if password_fields == 0:
        return False
        
    return True

def get_form_signature(url, fields):
    """Generate a signature for a form based on domain and field attributes"""
    domain = urllib.parse.urlparse(url).netloc
    # Include username field attributes to help identify the form
    field_signature = ""
    if fields["username"]:
        field_attrs = fields["username"][0].get("name", "") + fields["username"][0].get("placeholder", "")
        field_signature = re.sub(r'\W+', '', field_attrs.lower())
    return f"{domain}:{field_signature}"

async def handle_form(page, logger, worker_id):
    """Handle login forms by prompting user for credentials"""
    if not await has_login_form(page):
        return False
    
    logger.info(f"Worker {worker_id}: Login form detected on page {page.url}")
    
    current_url = page.url
    
    fields = await identify_form_fields(page)
    
    if not fields["username"] or not fields["password"]:
        logger.info(f"Worker {worker_id}: Form detected but doesn't appear to be a login form")
        return False
    
    # Check for cached credentials
    form_signature = get_form_signature(current_url, fields)
    cached_creds = credential_cache.get(form_signature)
    
    if cached_creds:
        # Use cached credentials
        logger.info(f"Worker {worker_id}: Using cached credentials for {urllib.parse.urlparse(current_url).netloc}")
        username = cached_creds["username"]
        password = cached_creds["password"]
        print(f"\nUsing cached credentials for {urllib.parse.urlparse(current_url).netloc}")
    else:
        # Prompt for credentials
        print("\n" + "="*60)
        print(f"Login form detected on {page.url}")
        print("="*60)
        
        # Get username input
        username_field = fields["username"][0]
        username_prompt = username_field.get('placeholder', '') or username_field.get('name', '') or 'username'
        username = input(f"Enter username/email ({username_prompt}): ")
        
        # Get password input
        password_field = fields["password"][0]
        password = input("Enter password: ")
    
    try:
        # Fill the form
        await page.fill(fields["username"][0]["selector"], username)
        await page.fill(fields["password"][0]["selector"], password)
        
        # Submit form
        if fields["submit"]:
            submit_selector = fields["submit"][0]["selector"]
            logger.info(f"Worker {worker_id}: Clicking submit button")
            
            await page.click(submit_selector)
            await page.wait_for_load_state('networkidle')
        else:
            logger.info(f"Worker {worker_id}: No submit button found, pressing Enter on password field")
            await page.press(fields["password"][0]["selector"], "Enter")
            await page.wait_for_load_state('networkidle')
            
        if page.url != current_url:
            logger.info(f"Worker {worker_id}: Successfully logged in! New URL: {page.url}")
            print("\nSuccessfully logged in!")
            
            # Cache successful credentials for future use
            if not cached_creds:  # Only cache if we didn't use cached creds already
                credential_cache[form_signature] = {"username": username, "password": password}
                logger.info(f"Worker {worker_id}: Cached credentials for future use")
            
            return True
        else:
            logger.warning(f"Worker {worker_id}: Form submitted but URL didn't change")
            print("\nForm submitted, but URL didn't change. Login might have failed.")
            return False
            
    except Exception as e:
        logger.error(f"Worker {worker_id}: Error during login: {e}")
        print(f"\nError during login: {e}")
        return False

def can_fetch(robot_parser, url):
    """Check if the URL is allowed to be fetched based on robots.txt"""
    if robot_parser:
        return robot_parser.can_fetch("*", url)
    return True

async def worker(queue: Queue, file_ext, output_dir, same_domain_only, playwright, worker_id, logger, robot_parser=None):
    logger.info(f"Worker {worker_id} starting")
    
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    
    # Set a custom user agent that includes your bot name
    await context.set_extra_http_headers({
        "User-Agent": "FileScraper/1.0 (+https://yourwebsite.com/bot)"
    })
    
    urls_processed = 0
    files_downloaded = 0
    idle_timeout = 20  # seconds to wait for new work

    try:
        while True:  
            try:
                url = await asyncio.wait_for(queue.get(), timeout=idle_timeout)
            except asyncio.TimeoutError:
                logger.info(f"Worker {worker_id}: No new URLs after {idle_timeout}s, shutting down")
                break
                
            urls_processed += 1

            async with visited_lock:
                if url in visited_urls or not is_valid_url(url):
                    logger.debug(f"Worker {worker_id}: Skipping already visited or invalid URL: {url}")
                    queue.task_done()
                    continue
                visited_urls.add(url)
            
            # Check robots.txt before processing URL
            if not can_fetch(robot_parser, url):
                logger.info(f"Worker {worker_id}: Skipping {url} - disallowed by robots.txt")
                queue.task_done()
                continue

            logger.debug(f"Worker {worker_id}: Processing URL {urls_processed}: {url}")

            try:
                if url.lower().endswith(f".{file_ext.lower()}"):
                    logger.debug(f"Worker {worker_id}: Direct file download detected: {url}")
                    await download_file(page, url, output_dir, logger)
                    files_downloaded += 1
                    queue.task_done()
                    continue
                
                logger.info(f"Worker {worker_id}: Visiting page: {url}")
                
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
                
                await page.goto(url, timeout=30000, wait_until='domcontentloaded')
                await page.wait_for_timeout(500)

                # Check if login form is present and handle it
                logged_in = await handle_form(page, logger, worker_id)
                if logged_in:
                    logger.info(f"Worker {worker_id}: Successfully authenticated")

                links = await page.eval_on_selector_all("a", "els => els.map(el => el.href)")
                new_links_added = 0
                
                for link in links:
                    if not is_valid_url(link):
                        continue
                    if same_domain_only and not is_internal_url(link):
                        continue
                    if not can_fetch(robot_parser, link):
                        logger.debug(f"Worker {worker_id}: Skipping {link} - disallowed by robots.txt")
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

def setup_robot_parser(start_url):
    """Setup robots.txt parser for the given start URL"""
    from urllib.robotparser import RobotFileParser
    parsed_url = urllib.parse.urlparse(start_url)
    robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
    robot_parser = RobotFileParser()
    robot_parser.set_url(robots_url)
    robot_parser.read()
    return robot_parser

async def main(args):
    global base_domain
    
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
    
    os.makedirs(args.output_dir, exist_ok=True)
    logger.info(f"Created/verified output directory: {args.output_dir}")

    queue = asyncio.Queue()
    await queue.put(args.start_url)
    logger.info("Added start URL to queue")

    # Setup robots.txt parser
    robot_parser = setup_robot_parser(args.start_url)

    start_time = datetime.now()
    
    async with async_playwright() as playwright:
        logger.info(f"Starting {args.threads} worker threads")
        await asyncio.gather(*[
            worker(queue, args.ext, args.output_dir, args.same_domain_only, playwright, i+1, logger, robot_parser)
            for i in range(args.threads)
        ])

        logger.info("All workers completed")
        

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