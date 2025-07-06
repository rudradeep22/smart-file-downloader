# File Scraper

A fast, async web scraper built with Playwright that can crawl websites and download files of specified extensions (PDF, CSV, etc.) while handling authentication forms.

## Features

- **Async crawling** with configurable worker threads
- **Smart authentication** - detects and handles login forms automatically
- **Credential caching** - remembers login credentials for similar forms
- **Robots.txt compliance** - respects website crawling policies
- **Download detection** - identifies direct file links and download URLs
- **Comprehensive logging** - detailed logs with multiple verbosity levels
- **Domain filtering** - option to crawl only within the same domain

## Installation

### Using uv (recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install
```

### Alternative: Using pip

```bash
pip install -r requirements.txt
playwright install
```

## Usage

### Basic Usage

```bash
# Download all PDF files from a website
uv run python file_scraper.py --start-url "https://example.com" --ext pdf

# Download CSV files to a specific directory
uv run python file_scraper.py --start-url "https://data.example.com" --ext csv --output-dir ./data

# Crawl only within the same domain
uv run python file_scraper.py --start-url "https://example.com" --ext pdf --same-domain-only
```

### Advanced Usage

```bash
# Use more worker threads for faster crawling
uv run python file_scraper.py --start-url "https://example.com" --ext pdf --threads 8

# Enable debug logging and save to file
uv run python file_scraper.py --start-url "https://example.com" --ext pdf --log-level DEBUG --log-file

# Download multiple file types (run separately for each extension)
uv run python file_scraper.py --start-url "https://example.com" --ext pdf
uv run python file_scraper.py --start-url "https://example.com" --ext csv
uv run python file_scraper.py --start-url "https://example.com" --ext xlsx
```

## Command Line Arguments

| Argument | Description | Default | Required |
|----------|-------------|---------|----------|
| `--start-url` | Starting URL to begin crawling | - | ✓ |
| `--ext` | File extension to search for | `pdf` | ✗ |
| `--output-dir` | Directory to save downloaded files | `downloads` | ✗ |
| `--same-domain-only` | Only crawl URLs within the same domain | `False` | ✗ |
| `--threads` | Number of concurrent worker threads | `4` | ✗ |
| `--log-level` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) | `INFO` | ✗ |
| `--log-file` | Enable logging to file | `False` | ✗ |

## Authentication

The scraper automatically detects login forms and will prompt you for credentials when needed:

1. When a login form is detected, you'll see a prompt asking for username/email and password
2. Credentials are cached for similar forms during the session
3. The scraper will attempt to log in and continue crawling authenticated areas

## Output

- Downloaded files are saved to the specified output directory (default: `downloads/`)
- Log files are created with timestamp: `file_scraper_YYYYMMDD_HHMMSS.log`
- Progress and statistics are displayed in the console

## Examples

### Download academic papers
```bash
uv run python file_scraper.py --start-url "https://example.com" --ext pdf --same-domain-only --threads 6
```

### Scrape data files with detailed logging
```bash
uv run python file_scraper.py --start-url "https://example.com" --ext csv --log-level DEBUG --log-file --output-dir ./government_data
```

### Download from password-protected site
```bash
uv run python file_scraper.py --start-url "https://example.com" --ext pdf
# The scraper will prompt for login credentials when it encounters the login form
```

## Notes

- The scraper respects `robots.txt` files
- Downloads are deduplicated - files won't be downloaded twice
- The scraper handles various download URL patterns and direct file links
- Credential caching works per domain and form signature
- Browser runs in headless mode for better performance

## Troubleshooting

**Installation Issues:**
```bash
# If uv installation fails, try:
uv pip install --upgrade pip
uv pip install -r requirements.txt

# If Playwright browsers aren't installed:
uv run playwright install chromium
```

**Permission Issues:**
```bash
# Make sure the output directory is writable
chmod 755 downloads/
```

**Memory Issues with Large Sites:**
```bash
# Reduce the number of worker threads
uv run python file_scraper.py --start-url "https://example.com" --threads 2
```

## Testing

The project includes comprehensive tests for robots.txt functionality, using mocked GitHub robots.txt behavior to test various URL patterns without making actual network requests.

### Running Tests

```bash
# Run all tests (uses mocked robots.txt behavior)
uv run python -m pytest test_robots_github_mock.py -v

# Run tests with detailed output
uv run python -m pytest test_robots_github_mock.py -v -s

# Run specific test methods
uv run python -m pytest test_robots_github_mock.py::TestRobotsGitHub::test_github_disallowed_search_urls -v

# Run tests using unittest directly
uv run python test_robots_github_mock.py
```

### Test Coverage

The test suite covers:

- **Basic robots.txt functionality** - Testing parser setup and URL validation with mocks
- **GitHub-specific robots.txt rules** - Mocked behavior based on GitHub's robots.txt patterns
- **Disallowed URL patterns** - Search, commits, tree, raw, archive, gist, pulse, projects, etc.
- **Allowed URL patterns** - Basic repository pages, releases, user profiles
- **Query parameter handling** - Testing various disallowed query parameters
- **Exception cases** - Special cases like tab=achievements URLs
- **Mock validation** - Ensures the robots.txt parser integration works correctly

### Test Implementation

The tests use `unittest.mock` to simulate robots.txt behavior without making network requests:
- Mock parser objects simulate GitHub's actual robots.txt rules
- Tests verify correct URL construction for robots.txt endpoints
- Mocked `can_fetch` behavior matches expected GitHub patterns
- No actual network calls are made during testing

### Example Test Output

```bash
$ uv run python test_robots_github_mock.py

test_can_fetch_with_none_parser (__main__.TestRobotsGitHub) ... ok
test_can_fetch_with_parser_allowed (__main__.TestRobotsGitHub) ... ok
test_can_fetch_with_parser_disallowed (__main__.TestRobotsGitHub) ... ok
test_github_allowed_basic_repo_urls (__main__.TestRobotsGitHub) ... ok
test_github_disallowed_projects_urls (__main__.TestRobotsGitHub) ... ok
test_github_disallowed_search_urls (__main__.TestRobotsGitHub) ... ok
...

Ran 11 tests in 0.012s

OK
```
