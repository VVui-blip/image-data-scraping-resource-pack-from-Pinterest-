# PinGrabber

[![PyPI version](https://img.shields.io/badge/pypi-v0.1.0-blue)](https://pypi.org/project/pingrabber/)
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

- Simple shortcut function – download an entire board with one line of code.
- Automatic conversion of thumbnail URLs to original high‑resolution images.
- Customizable output directory.
- Both high‑level wrapper and low‑level class for fine‑grained control.
- Built with `requests`, `BeautifulSoup`, and `lxml` for fast and reliable parsing.

---

## Installation

You can install PinGrabber directly from the GitHub repository:

```bash
pip install git+https://github.com/VVui-blip/image-data-scraping-resource-pack-from-Pinterest-.git
```

Alternatively, if you have the source code locally:

```bash
pip install -r requirements.txt
pip install .
```

Required dependencies (requests, beautifulsoup4, lxml) will be installed automatically.

---

Quick Start

`pingrabber.download(url)` **tự động nhận diện** URL bạn truyền vào là URL board hay URL pin đơn lẻ, và xử lý phù hợp — bạn không cần phân biệt thủ công.

### Tìm ảnh theo từ khóa (trả về link raw, không tải file)

```
import pingrabber

links = pingrabber.search("thiên nhiên")
for url in links:
    print(url)
```
Hàm này **không tải ảnh về máy** — nó chỉ trả về danh sách link ảnh gốc (raw) chất lượng cao. Bạn có thể dùng link đó để xem trước, lọc bớt, hoặc tự tải bằng `requests` nếu muốn.

> Cách hoạt động: `search()` dùng công cụ tìm kiếm (DuckDuckGo, không cần JS) với cú pháp `site:pinterest.com <từ khóa>` để tìm ra vài board liên quan, sau đó tự động chạy qua RSS của các board đó để lấy link ảnh — **không cào trực tiếp trang search của Pinterest**, vì trang đó cần JavaScript render mà `requests` không đọc được.

Tùy chỉnh số board quét và số ảnh mỗi board:

```python
links = pingrabber.search("nature", max_boards=5, max_images_per_board=10)
```
Download all images from a public Pinterest board to the default downloads/ folder:

```
import pingrabber

pingrabber.download("https://www.pinterest.com/username/boardname/")
```
for a single pin:

```
import pingrabber

pingrabber.download("https://www.pinterest.com/pin/119134352618387326/")
```
To save images to a custom directory:

```
import pingrabber

pingrabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="my_pinterest_images"
)
```

---

Advanced Usage

For more control, use the PinGrabber class:

```
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

```
from pingrabber import PinGrabber

grabber = PinGrabber()
rss_url = grabber.build_rss_url("https://www.pinterest.com/username/boardname/")
rss_content = grabber.fetch_rss(rss_url)
image_urls = grabber.extract_image_urls(rss_content)

for url in image_urls:
    print(url)
```

---

How It Works

1. Board URL to RSS Feed – The provided Pinterest board URL is converted to an RSS feed URL (appending .rss).
2. Fetch RSS – The RSS content is retrieved via a requests GET request.
3. Parse and Extract – BeautifulSoup with the lxml parser extracts all <img> tags inside the RSS items.
4. Upgrade to Original – Thumbnail URLs (e.g., 236x) are transformed into originals URLs to fetch the highest available quality.
5. Download – Each image is downloaded and saved to the specified output directory with a unique filename.

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
· lxml – Fast XML/HTML parser.

All dependencies are listed in requirements.txt and will be installed when using pip install . or the Git install command.

---

License

This project is released under the MIT License. See the LICENSE file for details.

Disclaimer: This tool is provided “as is”. You are solely responsible for ensuring that your usage complies with Pinterest’s Terms of Service and applicable copyright laws.

---

Built with attention for developers who need a quick, clean Pinterest image scraper.
