"""
pingrabber.core
~~~~~~~~~~~~~~~~

Logic chính: tải ảnh chất lượng cao từ Pinterest, hỗ trợ 2 dạng URL:

    1. URL BOARD (pinterest.com/<user>/<board>/):
       Lấy RSS feed của board, phân tích bằng BeautifulSoup để tìm các
       liên kết ảnh, sau đó tải ảnh gốc (chất lượng cao nhất) về máy.

    2. URL PIN ĐƠN LẺ (pinterest.com/pin/<id>/):
       Pin lẻ không có RSS feed riêng, nên thư viện sẽ fetch trực tiếp
       trang HTML của pin và lấy ảnh từ thẻ <meta property="og:image">.

Hàm `download()` / `PinGrabber.download()` tự động nhận diện loại URL
và xử lý phù hợp, người dùng không cần phân biệt thủ công.

Ghi chú kỹ thuật:
    Pinterest cung cấp RSS feed công khai cho mỗi board theo dạng:
        https://www.pinterest.com/<user>/<board>.rss

    Mỗi <item> trong feed chứa một đoạn HTML (trong <description>) có thẻ
    <img src="..."> trỏ tới ảnh thumbnail. URL ảnh thumbnail thường có dạng:
        https://i.pinimg.com/236x/xx/xx/xx/xxxxxxx.jpg

    Để lấy ảnh gốc (kích thước lớn nhất), ta thay thế phần kích thước
    (ví dụ "236x") bằng "originals".
"""

from __future__ import annotations

import os
import re
import time
import random
import logging
from typing import List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# `ddgs` (trước đây là `duckduckgo-search`) là dependency TÙY CHỌN, chỉ dùng
# cho tính năng search() theo từ khóa. Nếu chưa cài, search() sẽ tự động
# rơi về phương án dự phòng dùng requests + BeautifulSoup thuần.
try:
    from ddgs import DDGS  # package mới, khuyến nghị
    _HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # tên package cũ, vẫn còn trên PyPI
        _HAS_DDGS = True
    except ImportError:
        DDGS = None
        _HAS_DDGS = False

logger = logging.getLogger("pingrabber")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# Danh sách User-Agent thật để xoay vòng, giảm khả năng bị nhận diện là bot
# khi gọi đến công cụ tìm kiếm (search engine thường nhạy với UA hơn Pinterest).
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

# User-Agent mặc định dùng cho các request tải ảnh/RSS (ổn định, không cần xoay)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENTS[0],
}


def _random_search_headers() -> dict:
    """Tạo header ngẫu nhiên (User-Agent + Accept-Language) cho mỗi lần search,
    giúp giảm khả năng bị nhận diện và chặn theo pattern cố định."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "vi-VN,vi;q=0.9,en;q=0.8"]),
    }

# Regex để tìm URL ảnh i.pinimg.com bên trong đoạn HTML mô tả của RSS item
IMG_URL_PATTERN = re.compile(
    r"https?://i\.pinimg\.com/[^\s\"'<>]+\.(?:jpg|jpeg|png|gif|webp)",
    re.IGNORECASE,
)

# Các kích thước thumbnail phổ biến mà Pinterest dùng trong URL ảnh,
# cần thay bằng "originals" để lấy ảnh gốc chất lượng cao nhất.
THUMBNAIL_SIZE_PATTERN = re.compile(
    r"/(\d+x(?:\d+)?|originals)/", re.IGNORECASE
)

# Nhận diện URL pin đơn lẻ, ví dụ: pinterest.com/pin/119134352618387326/
SINGLE_PIN_PATTERN = re.compile(r"^/pin/(\d+)", re.IGNORECASE)

# Danh sách công cụ tìm kiếm để thử lần lượt (fallback) khi một engine bị
# chặn hoặc trả lỗi. Mỗi engine có format URL kết quả khác nhau nên cần
# parser riêng (xem hàm _parse_search_results).
SEARCH_ENGINES = [
    {
        "name": "duckduckgo_html",
        "url": "https://html.duckduckgo.com/html/",
        "param": "q",
    },
    {
        "name": "duckduckgo_lite",
        "url": "https://lite.duckduckgo.com/lite/",
        "param": "q",
    },
    {
        "name": "bing",
        "url": "https://www.bing.com/search",
        "param": "q",
    },
]

# Regex nhận diện URL board hợp lệ trong kết quả tìm kiếm:
# pinterest.com/<user>/<board>/ nhưng KHÔNG phải /pin/..., /search/..., /explore/...
BOARD_URL_PATTERN = re.compile(
    r"^https?://(?:[a-z]{2,3}\.)?pinterest\.[a-z.]+/"
    r"(?!pin/|search/|explore/|today/)([\w.\-%]+)/([\w.\-%]+)/?$",
    re.IGNORECASE,
)


class PinGrabberError(Exception):
    """Lỗi tùy biến cho thư viện pingrabber."""


class PinGrabber:
    """Đối tượng chính để cào và tải ảnh từ một board Pinterest."""

    def __init__(self, timeout: int = 15, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    # ------------------------------------------------------------------ #
    # Tiện ích: kiểm tra URL là pin đơn lẻ hay board
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_single_pin_url(url: str) -> bool:
        """Trả về True nếu URL có dạng pinterest.com/pin/<id>/ (pin đơn lẻ)."""
        parsed = urlparse(url)
        return bool(SINGLE_PIN_PATTERN.match(parsed.path))

    # ------------------------------------------------------------------ #
    # TÌM KIẾM THEO TỪ KHÓA
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_bing_real_url(href: str) -> Optional[str]:
        """Bing thường bọc link thật trong link redirect dạng base64
        (tham số 'u', tiền tố 'a1' + base64 của URL thật). Hàm này giải mã
        ra URL thật nếu có, ngược lại trả về href gốc không đổi."""
        import base64
        from urllib.parse import urlparse as _urlparse, parse_qs

        parsed = _urlparse(href)
        qs = parse_qs(parsed.query)
        if "u" in qs:
            raw = qs["u"][0]
            if raw.startswith("a1"):
                raw = raw[2:]
            # Bing dùng base64 URL-safe, có thể thiếu padding '='
            padding = "=" * (-len(raw) % 4)
            try:
                decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8", errors="ignore")
                return decoded
            except (ValueError, UnicodeDecodeError):
                return href
        return href

    def _parse_search_results(self, engine_name: str, html: str) -> List[str]:
        """Phân tích HTML kết quả tìm kiếm để lấy danh sách URL board hợp lệ.
        Mỗi engine có cấu trúc HTML khác nhau nên xử lý link hơi khác nhau."""
        soup = BeautifulSoup(html, "html.parser")
        board_urls: List[str] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if engine_name == "bing":
                href = self._extract_bing_real_url(href) or href

            match = BOARD_URL_PATTERN.match(href)
            if match:
                normalized = href.split("?")[0].rstrip("/") + "/"
                if normalized not in board_urls:
                    board_urls.append(normalized)

        return board_urls

    def _find_boards_via_ddgs(self, keyword: str, max_results: int = 5) -> List[str]:
        """
        Tìm board bằng package `ddgs` (trước đây là `duckduckgo-search`).

        Ưu điểm so với cách tự gọi requests:
            - Package được cộng đồng duy trì, tự xử lý header/cookie giống
              trình duyệt thật hơn, tỷ lệ bị chặn thấp hơn.
            - Hỗ trợ proxy (http/https/socks5) ngay trong constructor, đây
              là cách hiệu quả nhất để né chặn theo IP nếu bạn có proxy.
            - Tự động thử nhiều backend bên trong (DuckDuckGo, Bing, Google...).

        Trả về [] nếu ddgs chưa được cài, hoặc nếu gọi thất bại (lỗi sẽ
        được log lại, không raise, để find_boards() có thể rơi về fallback).
        """
        if not _HAS_DDGS:
            return []

        query = f"site:pinterest.com {keyword}"
        try:
            ddgs = DDGS(timeout=self.timeout)
            try:
                raw_results = ddgs.text(query, max_results=max_results * 3)
            finally:
                # Một số phiên bản DDGS hỗ trợ context manager / .close(),
                # đóng lại nếu có để giải phóng kết nối HTTP.
                close_fn = getattr(ddgs, "close", None)
                if callable(close_fn):
                    close_fn()
        except Exception as exc:  # noqa: BLE001 - ddgs có thể raise nhiều loại lỗi riêng
            logger.warning("  [ddgs] Gọi thất bại: %s", exc)
            return []

        board_urls: List[str] = []
        for item in raw_results or []:
            # Tùy phiên bản, key có thể là "href" hoặc "url"
            href = item.get("href") or item.get("url") or ""
            if not href:
                continue
            match = BOARD_URL_PATTERN.match(href)
            if match:
                normalized = href.split("?")[0].rstrip("/") + "/"
                if normalized not in board_urls:
                    board_urls.append(normalized)

        return board_urls[:max_results]

    def _find_boards_via_requests(
        self,
        keyword: str,
        max_results: int = 5,
        max_retries: int = 2,
        delay_seconds: float = 1.5,
    ) -> List[str]:
        """
        Phương án DỰ PHÒNG: tự gọi requests đến nhiều search engine, dùng khi
        package `ddgs` chưa được cài hoặc gọi thất bại. Có xoay User-Agent,
        retry, và fallback giữa nhiều engine (DuckDuckGo HTML/Lite, Bing).
        """
        query = f"site:pinterest.com {keyword}"
        last_error: Optional[Exception] = None

        for engine in SEARCH_ENGINES:
            for attempt in range(1, max_retries + 1):
                try:
                    headers = _random_search_headers()
                    resp = self.session.get(
                        engine["url"],
                        params={engine["param"]: query},
                        headers=headers,
                        timeout=self.timeout,
                    )

                    if resp.status_code in (403, 429):
                        logger.warning(
                            "  [%s] Bị chặn (HTTP %d), thử lại lần %d/%d...",
                            engine["name"], resp.status_code, attempt, max_retries,
                        )
                        time.sleep(delay_seconds + random.uniform(0, 1.5))
                        continue

                    resp.raise_for_status()

                    board_urls = self._parse_search_results(engine["name"], resp.text)
                    if board_urls:
                        logger.info(
                            "  [%s] Tìm thấy %d board.", engine["name"], len(board_urls)
                        )
                        return board_urls[:max_results]

                    logger.info("  [%s] Không có kết quả phù hợp, thử engine khác.", engine["name"])
                    break  # Engine trả về OK nhưng không có board -> chuyển engine khác

                except requests.RequestException as exc:
                    last_error = exc
                    logger.warning(
                        "  [%s] Lỗi request (lần %d/%d): %s",
                        engine["name"], attempt, max_retries, exc,
                    )
                    time.sleep(delay_seconds + random.uniform(0, 1.5))

            # Nghỉ một chút trước khi chuyển sang engine kế tiếp
            time.sleep(delay_seconds)

        if last_error:
            logger.error(
                "Tất cả công cụ tìm kiếm đều thất bại. Lỗi cuối: %s. "
                "Mạng của bạn có thể đang bị chặn truy cập search engine — "
                "hãy thử lại sau, đổi mạng/VPN, hoặc tự tìm board qua trình "
                "duyệt rồi dùng download(url_board) trực tiếp.",
                last_error,
            )
        return []

    def find_boards(
        self,
        keyword: str,
        max_results: int = 5,
        max_retries: int = 2,
        delay_seconds: float = 1.5,
    ) -> List[str]:
        """
        Tìm các URL board Pinterest liên quan đến từ khóa.

        Thứ tự ưu tiên:
            1. Dùng package `ddgs` (khuyến nghị) nếu đã cài — package này
               được cộng đồng duy trì, tự xử lý giả lập trình duyệt tốt
               hơn và hỗ trợ proxy, nên tỷ lệ bị chặn thấp hơn nhiều.
            2. Nếu chưa cài `ddgs` hoặc gọi thất bại, tự động rơi về
               phương án dự phòng: gọi requests trực tiếp đến nhiều search
               engine (DuckDuckGo HTML/Lite, Bing), có xoay User-Agent,
               retry và delay giữa các lần thử.

        Để dùng phương án 1 (khuyến nghị), cài thêm:
            pip install ddgs

        Lưu ý: đây KHÔNG phải tìm kiếm trực tiếp trong Pinterest (trang đó
        cần JS render nên requests không đọc được), mà là dùng index của
        công cụ tìm kiếm để tìm ra các board công khai liên quan. Kết quả
        có thể rỗng tùy theo IP/mạng của bạn — nếu vậy, hãy tự tìm board
        qua trình duyệt và dùng download(url_board) trực tiếp.

        Trả về danh sách URL board (đã loại trùng), tối đa max_results.
        """
        if _HAS_DDGS:
            logger.info("Đang tìm board qua package ddgs...")
            board_urls = self._find_boards_via_ddgs(keyword, max_results=max_results)
            if board_urls:
                logger.info("  [ddgs] Tìm thấy %d board.", len(board_urls))
                return board_urls
            logger.info("  [ddgs] Không có kết quả, chuyển sang phương án dự phòng (requests).")
        else:
            logger.info(
                "Package 'ddgs' chưa được cài (pip install ddgs) — "
                "dùng phương án dự phòng qua requests."
            )

        return self._find_boards_via_requests(
            keyword,
            max_results=max_results,
            max_retries=max_retries,
            delay_seconds=delay_seconds,
        )

    def search(
        self,
        keyword: str,
        max_boards: int = 3,
        max_images_per_board: int = 25,
        max_retries: int = 2,
        delay_seconds: float = 1.5,
    ) -> List[str]:
        """
        Tìm board liên quan đến từ khóa, rồi tự động lấy danh sách URL ảnh
        gốc (chất lượng cao) từ các board đó. KHÔNG tải ảnh về máy, chỉ
        trả về danh sách link raw để bạn tự quyết định dùng tiếp.

        Ví dụ:
            import pingrabber
            links = pingrabber.search("thiên nhiên")
            print(links)  # ['https://i.pinimg.com/originals/.../a.jpg', ...]

        Args:
            keyword: từ khóa tìm kiếm, ví dụ "thiên nhiên", "nature".
            max_boards: số board tối đa sẽ quét qua.
            max_images_per_board: số ảnh tối đa lấy từ mỗi board.
            max_retries: số lần thử lại mỗi search engine nếu bị chặn/lỗi.
            delay_seconds: thời gian nghỉ cơ bản (giây) giữa các lần thử,
                giúp giảm khả năng bị search engine chặn vì gọi quá nhanh.

        Trả về danh sách URL ảnh gốc (string), rỗng nếu không tìm được gì.
        Nếu trả về rỗng, kiểm tra log WARNING/ERROR để biết nguyên nhân cụ
        thể (bị chặn, hết engine, hay không có board liên quan).
        """
        logger.info("Đang tìm board liên quan đến từ khóa: %s", keyword)
        board_urls = self.find_boards(
            keyword,
            max_results=max_boards,
            max_retries=max_retries,
            delay_seconds=delay_seconds,
        )

        if not board_urls:
            logger.warning(
                "Không tìm thấy board nào liên quan đến: %s. "
                "Nếu log phía trên cho thấy lỗi 403/429 ở tất cả engine, "
                "khả năng cao mạng/IP của bạn đang bị search engine chặn.",
                keyword,
            )
            return []

        logger.info("Tìm thấy %d board, đang lấy ảnh...", len(board_urls))

        all_image_urls: List[str] = []
        for board_url in board_urls:
            try:
                rss_url = self.build_rss_url(board_url)
                rss_content = self.fetch_rss(rss_url)
                image_urls = self.extract_image_urls(rss_content)[:max_images_per_board]
                logger.info("  + %s -> %d ảnh", board_url, len(image_urls))
                for url in image_urls:
                    if url not in all_image_urls:
                        all_image_urls.append(url)
                # Delay nhẹ giữa các board để tránh gửi request quá dồn dập
                time.sleep(delay_seconds * 0.5)
            except PinGrabberError as exc:
                logger.error("  Lỗi khi xử lý board %s: %s", board_url, exc)

        logger.info("Hoàn tất. Tổng cộng %d link ảnh raw.", len(all_image_urls))
        return all_image_urls

    # ------------------------------------------------------------------ #
    # Bước 1: Chuyển URL board thường -> URL RSS feed
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_rss_url(board_url: str) -> str:
        """
        Chuyển một URL board Pinterest thông thường thành URL RSS feed.

        Ví dụ:
            https://www.pinterest.com/username/boardname/
            -> https://www.pinterest.com/username/boardname.rss
        """
        parsed = urlparse(board_url)
        if "pinterest." not in parsed.netloc:
            raise PinGrabberError(f"URL không hợp lệ, không phải Pinterest: {board_url}")

        path = parsed.path.strip("/")
        if not path:
            raise PinGrabberError(f"Không tìm thấy đường dẫn board trong URL: {board_url}")

        if path.endswith(".rss"):
            rss_path = path
        else:
            rss_path = f"{path}.rss"

        return f"https://{parsed.netloc}/{rss_path}"

    # ------------------------------------------------------------------ #
    # Bước 2: Lấy nội dung RSS feed
    # ------------------------------------------------------------------ #
    def fetch_rss(self, rss_url: str) -> str:
        """Gửi request lấy nội dung RSS feed (dạng XML/text)."""
        try:
            resp = self.session.get(rss_url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise PinGrabberError(f"Không thể tải RSS feed: {rss_url} ({exc})") from exc
        return resp.text

    # ------------------------------------------------------------------ #
    # Bước 3: Parse RSS bằng BeautifulSoup -> lấy danh sách URL ảnh gốc
    # ------------------------------------------------------------------ #
    def extract_image_urls(self, rss_content: str) -> List[str]:
        """
        Dùng BeautifulSoup để parse XML của RSS feed, lấy tất cả thẻ <img>
        nằm trong mỗi <item><description>, rồi nâng cấp URL thumbnail
        thành URL ảnh gốc ("originals").
        """
        soup = BeautifulSoup(rss_content, "lxml-xml")
        items = soup.find_all("item")

        if not items:
            # Một số feed có thể không parse đúng theo "lxml-xml" (hiếm),
            # thử lại bằng parser HTML mặc định như phương án dự phòng.
            soup = BeautifulSoup(rss_content, "html.parser")
            items = soup.find_all("item")

        image_urls: List[str] = []

        for item in items:
            description = item.find("description")
            if not description or not description.text:
                continue

            # description chứa HTML dạng escape, parse tiếp lần 2
            desc_soup = BeautifulSoup(description.text, "html.parser")
            img_tags = desc_soup.find_all("img")

            for img in img_tags:
                src = img.get("src")
                if not src:
                    continue
                # Nâng cấp sang ảnh gốc
                original_url = THUMBNAIL_SIZE_PATTERN.sub("/originals/", src)
                if original_url not in image_urls:
                    image_urls.append(original_url)

        return image_urls

# ------------------------------------------------------------------ #
# CÁC HÀM TIỆN ÍCH ĐỘC LẬP (SHORTCUT WRAPPERS)
# ------------------------------------------------------------------ #

def download(
    url: str, 
    output_dir: str = "pinterest_images", 
    timeout: int = 15
) -> List[str]:
    """Hàm tiện ích nhanh: tự động nhận diện và tải ảnh từ Pin hoặc Board."""
    grabber = PinGrabber(timeout=timeout)
    return grabber.download(url, output_dir=output_dir)


def search(
    keyword: str,
    max_boards: int = 3,
    max_images_per_board: int = 25,
    max_retries: int = 2,
    delay_seconds: float = 1.5,
    timeout: int = 15,
) -> List[str]:
    """
    Hàm tiện ích nhanh: tìm board liên quan đến từ khóa và trả về danh sách
    link ảnh raw (chất lượng gốc), không tải file về máy.
    """
    grabber = PinGrabber(timeout=timeout)
    return grabber.search(
        keyword,
        max_boards=max_boards,
        max_images_per_board=max_images_per_board,
        max_retries=max_retries,
        delay_seconds=delay_seconds,
    )
