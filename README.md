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

## How It Works

1. Board/Pin URL to RSS Feed – The provided URL is converted to an RSS feed URL (appending .rss for boards, or using the pin’s RSS endpoint).
2. Fetch RSS – The RSS content is retrieved via a requests GET request.
3. Parse and Extract – BeautifulSoup with the lxml parser extracts all <img> tags inside the RSS items.
4. Upgrade to Original – Thumbnail URLs (e.g., 236x) are transformed into originals URLs to fetch the highest available quality.
5. Download – Each image is downloaded and saved to the specified output directory with a unique filename.

---

## Project Structure

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

## Dependencies

· Python 3.7+
· requests – HTTP requests.
· beautifulsoup4 – HTML/XML parsing.
· lxml – Fast XML/HTML parser.

All dependencies are listed in requirements.txt and will be installed when using pip install . or the Git install command.

---

## License

This project is released under the MIT License. See the LICENSE file for details.

Disclaimer: This tool is provided “as is”. You are solely responsible for ensuring that your usage complies with Pinterest’s Terms of Service and applicable copyright laws.

---

Built with attention for developers who need a quick, clean Pinterest image scraper.
