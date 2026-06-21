# PinGrabber

[![PyPI version](https://img.shields.io/badge/pypi-v1.0.2-blue)](https://pypi.org/project/pingrabber/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-green.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**PinGrabber** is a lightweight Python library that scrapes high‑quality images from any public Pinterest board using the official RSS feed provided by Pinterest. It extracts the original, full‑resolution images and downloads them to your local machine with minimal effort.

![Pinterest Banner](https://www.logo.wine/a/logo/Pinterest/Pinterest-Icon-White-Dark-Background-Logo.wine.svg)

> **Important** – Use this tool only with public boards and for personal or educational purposes. Always respect Pinterest’s [Terms of Service](https://www.pinterest.com/terms/) and the copyright of image authors.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Advanced Usage](#advanced-usage)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [License](#license)

---

## Features

- Simple shortcut function – download an entire board or a single pin with one line of code.
- Automatic conversion of thumbnail URLs to original high‑resolution images.
- Customizable output directory.
- Both high‑level wrapper and low‑level class for fine‑grained control.
- Keyword search that returns raw image URLs without downloading.
- Built with `requests`, `BeautifulSoup`, and `lxml` for fast and reliable parsing.

---

## Installation

You can install PinGrabber directly from the Pypi repository:
```bash
pip install pingrabber
```
or GitHub repository:
```bash
pip install git+https://github.com/VVui-blip/image-data-scraping-resource-pack-from-Pinterest-.git
```

Alternatively, if you have the source code locally:

```bash
pip install -r requirements.txt
pip install .
```

The required dependencies (requests, beautifulsoup4, lxml) will be installed automatically.

Optional dependency for better keyword search

For a more robust and stable keyword search, we recommend installing the ddgs package (community‑maintained, formerly duckduckgo-search):

```bash
pip install ddgs
```

Or install it together with PinGrabber:

```bash
pip install .[search]
```

ddgs provides a more reliable way to query search engines (DuckDuckGo, Bing, Google, etc.) and supports proxy configuration right in the code. Without ddgs, the search() function will fall back to direct requests calls to search engines, which are more prone to blocking.

---

## Quick Start

pingrabber.download(url) automatically detects whether the given URL is a board or a single pin and handles it accordingly – you don't need to differentiate manually.

Download all images from a board

```python
import pingrabber

pingrabber.download("https://www.pinterest.com/username/boardname/")
```

Download a single pin

```python
import pingrabber

pingrabber.download("https://www.pinterest.com/pin/119134352618387326/")
```

To save images to a custom directory:

```python
import pingrabber

pingrabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="my_pinterest_images"
)
```

Search images by keyword (returns raw links, no download)

```python
import pingrabber

links = pingrabber.search("nature")
for url in links:
    print(url)
```

This function does not download any images – it only returns a list of high‑quality raw image URLs. You can preview them, filter, or download them manually with requests if needed.

How it works: search() tries multiple search engines (DuckDuckGo HTML, DuckDuckGo Lite, Bing) using the site:pinterest.com <keyword> query. It rotates user‑agents, retries, and adds delays between attempts to reduce the chance of being blocked. If one engine fails (403/429), it automatically switches to the next. It does not scrape Pinterest’s search page directly, because that page requires JavaScript rendering which requests cannot handle.

Customise the number of boards to scan, images per board, retries, and delay:

```python
links = pingrabber.search(
    "nature",
    max_boards=5,
    max_images_per_board=10,
    max_retries=3,
    delay_seconds=2.5
)
```

If search() always returns empty: check the logged WARNING/ERROR messages. If you see 403/429 errors for all fallback engines, your network/IP is likely being rate‑limited by the search engines (common on cloud servers, VPNs, or IPs that have sent many requests). In that case:

· Install ddgs if you haven’t (pip install ddgs) – this is the most significant improvement.
· If ddgs is installed but still returns nothing, try using a proxy directly with the package:
  ```python
  from ddgs import DDGS
  with DDGS(proxy="socks5://127.0.0.1:9050", timeout=15) as ddgs:
      results = ddgs.text("site:pinterest.com nature", max_results=5)
      print(results)
  ```
  If that returns results, you can initialise PinGrabber with a similarly proxied session, or simply use the found board URLs with download().
· Increase max_retries and delay_seconds (this only affects the fallback method).
· Try a different network/VPN.
· Alternatively, use the most reliable approach: find a board manually through your browser and call pingrabber.download(board_url) directly – this does not depend on search engines and is always stable.

---

## Advanced Usage

For more control, use the PinGrabber class:

```python
from pingrabber import PinGrabber

grabber = PinGrabber(timeout=30)

# Download all original images
saved_files = grabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="high_res_pins"
)

print(f"Downloaded {len(saved_files)} images")
```

If you only need the image URLs (without downloading):

```python
from pingrabber import PinGrabber

grabber = PinGrabber()
rss_url = grabber.build_rss_url("https://www.pinterest.com/username/boardname/")
rss_content = grabber.fetch_rss(rss_url)
image_urls = grabber.extract_image_urls(rss_content)

for url in image_urls:
    print(url)
```

---

```markdown
# PinGrabber

[![PyPI version](https://img.shields.io/badge/pypi-v1.0.2-blue)](https://pypi.org/project/pingrabber/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-green.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**PinGrabber** is a lightweight Python library that scrapes high‑quality images from public Pinterest boards, single pins, and even short links (pin.it/xxxx). It leverages Pinterest’s official RSS feeds for boards and directly parses HTML for individual pins, extracting full‑resolution originals with minimal effort.

![Pinterest Banner](https://www.logo.wine/a/logo/Pinterest/Pinterest-Icon-White-Dark-Background-Logo.wine.svg)

> **Important** – Use this tool only with public boards and for personal or educational purposes. Always respect Pinterest’s [Terms of Service](https://www.pinterest.com/terms/) and the copyright of image authors.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Advanced Usage](#advanced-usage)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [License](#license)

---

## Features

- **Multi‑URL support** – works with board URLs, single pin URLs, and Pinterest short links (`pin.it/xxxx`).
- **One‑line download** – download an entire board or a single pin with a single function call.
- **Automatic quality upgrade** – thumbnail URLs (e.g., `236x`) are replaced with `originals` to fetch the highest available resolution.
- **Keyword search** – find images by topic without downloading; returns raw image URLs.
- **Resilient search** – uses the optional `ddgs` package (community‑maintained) for stable search, falling back to direct HTTP requests against multiple search engines (Brave, Mojeek, Yandex, Startpage, Ecosia, Qwant, Gibiru, Ask, Yahoo) with automatic retries, User‑Agent rotation, and delays.
- **Customisable** – set output directory, timeout, number of boards/images, retry attempts, and delay.
- **Detailed logging** – colourful console output with clear progress and error messages.
- **Lightweight** – built on `requests`, `BeautifulSoup`, and `lxml` for speed and reliability.

---

## Installation

Install directly from PyPI (recommended):

```bash
pip install pingrabber
```

Or from the GitHub repository:

```bash
pip install git+https://github.com/VVui-blip/image-data-scraping-resource-pack-from-Pinterest-.git
```

If you have the source code locally:

```bash
pip install -r requirements.txt
pip install .
```

The required dependencies (requests, beautifulsoup4, lxml) are installed automatically.

Optional dependency for better keyword search

For a more robust keyword search, we highly recommend installing the ddgs package:

```bash
pip install ddgs
```

Or install it together with PinGrabber:

```bash
pip install .[search]
```

ddgs (formerly duckduckgo-search) provides a stable way to query multiple search engines (DuckDuckGo, Bing, Google, etc.) and supports proxy configuration directly in code. Without it, the search() function falls back to direct HTTP requests, which are more prone to rate‑limiting and blocking.

---

Quick Start

pingrabber.download(url) automatically detects the URL type – board, single pin, or short link – and handles it accordingly. You do not need to differentiate manually.

Download all images from a board

```python
import pingrabber

pingrabber.download("https://www.pinterest.com/username/boardname/")
```

Download a single pin

```python
import pingrabber

pingrabber.download("https://www.pinterest.com/pin/119134352618387326/")
```

Download from a short link (pin.it)

```python
import pingrabber

pingrabber.download("https://pin.it/3MKmfwvjG")  # automatically resolves to full URL
```

Save to a custom directory

```python
import pingrabber

pingrabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="my_pinterest_images"
)
```

Search images by keyword (returns raw links, no download)

```python
import pingrabber

links = pingrabber.search("nature")
for url in links:
    print(url)
```

This function does not download any images – it only returns a list of high‑quality raw image URLs. You can preview, filter, or download them manually.

How search() works:

· If ddgs is installed, it uses that first (most stable).
· Otherwise, it tries a chain of search engines (Brave, Mojeek, Yandex, Startpage, Ecosia, Qwant, Gibiru, Ask, Yahoo) with the query site:pinterest.com <keyword>.
· It rotates User‑Agents, retries on errors (403/429), and inserts random delays to avoid blocking.
· It does not scrape Pinterest’s own search page, because that requires JavaScript.

Customise the search parameters:

```python
links = pingrabber.search(
    "nature",
    max_boards=5,               # number of boards to scan
    max_images_per_board=10,    # images per board
    max_retries=3,              # retries per engine on failure
    delay_seconds=2.5           # base delay between attempts
)
```

If search() always returns empty, check the log output. 403/429 errors indicate your IP is being rate‑limited by search engines. Solutions:

· Install ddgs – it is much more resilient.
· If ddgs is installed and still fails, try using a proxy (see example below).
· Increase max_retries and delay_seconds (affects the fallback method only).
· Change your network or VPN.
· Or simply find a board manually in your browser and call download(board_url) directly – this is always stable.

Proxy example with ddgs (independent of PinGrabber):

```python
from ddgs import DDGS
with DDGS(proxy="socks5://127.0.0.1:9050", timeout=15) as ddgs:
    results = ddgs.text("site:pinterest.com nature", max_results=5)
    print(results)
```

---

Advanced Usage

For more fine‑grained control, instantiate the PinGrabber class:

```python
from pingrabber import PinGrabber

grabber = PinGrabber(timeout=30)

# Download all original images from a board
saved_files = grabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="high_res_pins"
)

print(f"Downloaded {len(saved_files)} images")
```

If you only need the image URLs (without downloading):

```python
from pingrabber import PinGrabber

grabber = PinGrabber()
rss_url = grabber.build_rss_url("https://www.pinterest.com/username/boardname/")
rss_content = grabber.fetch_rss(rss_url)
image_urls = grabber.extract_image_urls(rss_content)

for url in image_urls:
    print(url)
```

You can also use the low‑level methods for custom workflows, e.g., resolving short links manually:

```python
resolved = grabber.resolve_short_link("https://pin.it/3MKmfwvjG")
print(resolved)  # full Pinterest URL
```

---

How It Works

1. URL detection – The library automatically identifies whether the input is a board, a single pin, or a short link.
2. Short link resolution – If it’s a pin.it short link, it follows the redirect to obtain the full Pinterest URL.
3. Board handling – Converts the board URL to its RSS feed (appending .rss), fetches the XML, and parses all <img> tags inside each <item><description>.
4. Single pin handling – Fetches the pin’s HTML page directly and extracts the main image from the <meta property="og:image"> tag (already an original‑quality URL).
5. Quality upgrade – For board images, all thumbnail URLs (e.g., 236x) are transformed to originals to retrieve the highest available resolution.
6. Download – Each image is downloaded and saved to the specified output directory with a unique filename.

---

Project Structure

```
pin_grabber/
├── pingrabber/
│   ├── __init__.py          # Package entry point
│   └── core.py              # Main logic (PinGrabber class + helper functions)
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── setup.py                 # Packaging configuration
└── LICENSE                  # MIT License
```

---

Dependencies

· Python 3.7+
· requests – HTTP requests.
· beautifulsoup4 – HTML/XML parsing.
· lxml – Fast XML/HTML parser (used by BeautifulSoup).

All dependencies are listed in requirements.txt and are installed automatically with pip install . or pip install pingrabber.

---

License

This project is released under the MIT License. See the LICENSE file for details.

Disclaimer: This tool is provided “as is”. You are solely responsible for ensuring that your usage complies with Pinterest’s Terms of Service and applicable copyright laws.

---

Built with ❤️ by VVui-blip – a quick, clean Pinterest image scraper for developers.
