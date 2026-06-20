# pingrabber

Thư viện Python đơn giản giúp **cào ảnh chất lượng cao từ một board Pinterest công khai**, thông qua RSS feed mà Pinterest cung cấp sẵn.

> ⚠️ Lưu ý: Chỉ nên dùng với các board Pinterest công khai và cho mục đích cá nhân/học tập. Hãy tuân thủ Điều khoản dịch vụ của Pinterest và quyền sở hữu của tác giả ảnh.

---

## 1. Cài đặt

### Cài từ source (thư mục hiện tại)

```bash
pip install -r requirements.txt
pip install .
```

### Hoặc cài thủ công các thư viện cần thiết

```bash
pip install requests beautifulsoup4 lxml
```

---

## 2. Cách sử dụng

### Cách nhanh nhất — dùng hàm shortcut

```python
import pingrabber

pingrabber.download("https://www.pinterest.com/username/boardname/")
```

Ảnh sẽ được tự động tải về thư mục `downloads/` trong thư mục hiện tại.

### Tùy chỉnh thư mục lưu ảnh

```python
import pingrabber

pingrabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="anh_pinterest"
)
```

### Dùng class `PinGrabber` để kiểm soát chi tiết hơn

```python
from pingrabber import PinGrabber

grabber = PinGrabber(timeout=20)

# Tải toàn bộ ảnh gốc về thư mục chỉ định
saved_files = grabber.download(
    "https://www.pinterest.com/username/boardname/",
    output_dir="anh_pinterest"
)

print(f"Đã tải {len(saved_files)} ảnh")
```

### Chỉ lấy danh sách URL ảnh (không tải về)

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

## 3. Cách hoạt động

1. Chuyển URL board Pinterest thành URL RSS feed (dạng `.rss`).
2. Gửi request bằng `requests` để lấy nội dung RSS.
3. Dùng `beautifulsoup4` (kết hợp `lxml`) để phân tích RSS và trích xuất các thẻ `<img>`.
4. Nâng cấp URL ảnh thumbnail (vd: `236x`) thành URL ảnh gốc (`originals`) để có chất lượng cao nhất.
5. Tải toàn bộ ảnh về thư mục bạn chỉ định.

---

## 4. Cấu trúc thư mục package

```
pin_grabber/
├── pingrabber/
│   ├── __init__.py
│   └── core.py
├── requirements.txt
├── README.md
└── setup.py
```

---

## 5. Giấy phép

Phát hành theo giấy phép MIT. Sử dụng tự chịu trách nhiệm về việc tuân thủ điều khoản dịch vụ của Pinterest.
