"""
pingrabber
==========

Thư viện đơn giản giúp cào (scrape) ảnh chất lượng cao từ một board
Pinterest công khai thông qua RSS feed của Pinterest.

Cách dùng nhanh:

    import pingrabber

    pingrabber.download("https://www.pinterest.com/username/boardname/")

"""

from .core import PinGrabber, download

__all__ = ["PinGrabber", "download"]

__version__ = "0.1.0"
