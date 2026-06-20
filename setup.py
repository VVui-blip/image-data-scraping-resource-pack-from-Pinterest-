"""
setup.py
~~~~~~~~

File cấu hình để đóng gói và phát hành package `pingrabber` lên PyPI.

Cách build và publish (tham khảo):
    python setup.py sdist bdist_wheel
    twine upload dist/*
"""

import os
from setuptools import setup, find_packages

HERE = os.path.abspath(os.path.dirname(__file__))

# Đọc nội dung README.md để dùng làm long_description trên PyPI
with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# Đọc danh sách dependency từ requirements.txt, tách riêng phần BẮT BUỘC
# (core) và phần TÙY CHỌN (ddgs, chỉ cần cho tính năng search nâng cao).
with open(os.path.join(HERE, "requirements.txt"), encoding="utf-8") as f:
    all_requirements = [
        line.strip()
        for line in f
        if line.strip() and not line.strip().startswith("#")
    ]

requirements = [r for r in all_requirements if not r.lower().startswith("ddgs")]
search_extra = [r for r in all_requirements if r.lower().startswith("ddgs")]

setup(
    name="pingrabber",
    version="0.1.7",
    description="Thư viện cào ảnh chất lượng cao từ board Pinterest công khai qua RSS feed.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="VVui-blip",
    author_email="vuv54581@gmail.com",
    url="https://github.com/VVui-blip/pin_grabber",
    license="MIT",
    packages=find_packages(exclude=("tests", "tests.*")),
    install_requires=requirements,
    extras_require={
        # pip install pingrabber[search] -> cài thêm ddgs để search() ổn định hơn
        "search": search_extra,
    },
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="pinterest scraper rss image downloader",
    project_urls={
        "Source": "https://github.com/yourusername/pin_grabber",
        "Bug Reports": "https://github.com/yourusername/pin_grabber/issues",
    },
)
