"""
pingrabber
==========

Thư viện đơn giản giúp cào (scrape) ảnh chất lượng cao từ một board
Pinterest công khai thông qua RSS feed của Pinterest.

Cách dùng nhanh:

    import pingrabber

    # Tải ảnh từ board hoặc pin đơn lẻ (tự nhận diện loại URL)
    pingrabber.download("https://www.pinterest.com/username/boardname/")

    # Tìm theo từ khóa, lấy link ảnh raw (không tải file về máy)
    links = pingrabber.search("thiên nhiên")

"""

from .core import PinGrabber, download, search

__all__ = ["PinGrabber", "download", "search"]

__version__ = "0.1.6"
