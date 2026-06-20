"""
pingrabber.core
~~~~~~~~~~~~~~~~

Logic chính: lấy RSS feed của một board Pinterest, phân tích HTML bằng
BeautifulSoup để tìm các liên kết ảnh, sau đó tải ảnh gốc (chất lượng cao
nhất) về máy.

Ghi chú:
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
import logging
from typing import List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("pingrabber")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# User-Agent giả lập trình duyệt thật để tránh bị Pinterest chặn request
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
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


class PinGrabberError(Exception):
    """Lỗi tùy biến cho thư viện pingrabber."""


class PinGrabber:
    """Đối tượng chính để cào và tải ảnh từ một board Pinterest."""

    def __init__(self, timeout: int = 15, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

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
                original_url = self._to_original_quality(src)
                if original_url not in image_urls:
                    image_urls.append(original_url)

            # Phòng trường hợp ảnh nằm trong text thay vì thẻ <img>
            for match in IMG_URL_PATTERN.findall(description.text):
                original_url = self._to_original_quality(match)
                if original_url not in image_urls:
                    image_urls.append(original_url)

        return image_urls

    @staticmethod
    def _to_original_quality(image_url: str) -> str:
        """Thay phần kích thước thumbnail (vd: 236x) bằng 'originals'."""
        return THUMBNAIL_SIZE_PATTERN.sub("/originals/", image_url, count=1)

    # ------------------------------------------------------------------ #
    # Bước 4: Tải ảnh về máy
    # ------------------------------------------------------------------ #
    def download_image(self, image_url: str, output_dir: str) -> str:
        """Tải một ảnh về thư mục output_dir, trả về đường dẫn file đã lưu."""
        filename = os.path.basename(urlparse(image_url).path) or "image.jpg"
        filepath = os.path.join(output_dir, filename)

        try:
            resp = self.session.get(image_url, timeout=self.timeout, stream=True)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise PinGrabberError(f"Không thể tải ảnh: {image_url} ({exc})") from exc

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return filepath

    # ------------------------------------------------------------------ #
    # Hàm tổng hợp: từ URL board -> tải toàn bộ ảnh gốc về máy
    # ------------------------------------------------------------------ #
    def download(self, board_url: str, output_dir: str = "downloads") -> List[str]:
        """
        Quy trình đầy đủ:
            1. Tạo URL RSS từ URL board.
            2. Tải nội dung RSS.
            3. Trích xuất danh sách URL ảnh gốc chất lượng cao.
            4. Tải toàn bộ ảnh về output_dir.

        Trả về danh sách đường dẫn các file ảnh đã lưu thành công.
        """
        os.makedirs(output_dir, exist_ok=True)

        rss_url = self.build_rss_url(board_url)
        logger.info("Đang lấy RSS feed: %s", rss_url)

        rss_content = self.fetch_rss(rss_url)
        image_urls = self.extract_image_urls(rss_content)

        if not image_urls:
            logger.warning("Không tìm thấy ảnh nào trong board: %s", board_url)
            return []

        logger.info("Tìm thấy %d ảnh. Bắt đầu tải...", len(image_urls))

        saved_paths: List[str] = []
        for index, url in enumerate(image_urls, start=1):
            try:
                path = self.download_image(url, output_dir)
                saved_paths.append(path)
                logger.info("(%d/%d) Đã tải: %s", index, len(image_urls), path)
            except PinGrabberError as exc:
                logger.error("(%d/%d) Lỗi tải ảnh: %s", index, len(image_urls), exc)

        logger.info("Hoàn tất. Đã tải %d/%d ảnh.", len(saved_paths), len(image_urls))
        return saved_paths


# ---------------------------------------------------------------------- #
# Hàm shortcut cấp module để dùng nhanh: pingrabber.download(url)
# ---------------------------------------------------------------------- #
def download(board_url: str, output_dir: str = "downloads", timeout: int = 15) -> List[str]:
    """
    Hàm tiện ích nhanh, không cần khởi tạo PinGrabber thủ công.

    Ví dụ:
        import pingrabber
        pingrabber.download("https://www.pinterest.com/username/boardname/")
    """
    grabber = PinGrabber(timeout=timeout)
    return grabber.download(board_url, output_dir=output_dir)
