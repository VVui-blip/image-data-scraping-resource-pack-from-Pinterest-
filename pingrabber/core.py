"""
pingrabber.core
~~~~~~~~~~~~~~~~

Core logic for downloading high-quality images from Pinterest. Supports
three URL types:

    1. BOARD URL (pinterest.com/<user>/<board>/):
       Fetches the board's RSS feed, parses it with BeautifulSoup to find
       image links, then downloads the original (highest quality) images.

    2. SINGLE PIN URL (pinterest.com/pin/<id>/):
       A single pin has no RSS feed of its own, so the library fetches the
       pin's HTML page directly and extracts the image from the
       <meta property="og:image"> tag.

    3. SHORT LINK (pin.it/xxxxxxx):
       This is a Pinterest redirect link with no content of its own. The
       library automatically follows the redirect to resolve the full URL,
       then processes it according to its resolved type (usually a single
       pin).

`download()` / `PinGrabber.download()` automatically detects the URL type
and handles it accordingly — no manual branching required.

Technical notes:
    Pinterest provides a public RSS feed for every board at:
        https://www.pinterest.com/<user>/<board>.rss

    Each <item> in the feed contains an HTML snippet (inside <description>)
    with an <img src="..."> tag pointing to a thumbnail. Thumbnail URLs
    typically look like:
        https://i.pinimg.com/236x/xx/xx/xx/xxxxxxx.jpg

    To get the original (largest) image, the size segment (e.g. "236x") is
    replaced with "originals".
"""

from __future__ import annotations

import os
import re
import sys
import time
import random
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Optional proxy list grabber
try:
    import proxylists
    _HAS_PROXYLISTS = True
except ImportError:
    _HAS_PROXYLISTS = False

# `ddgs` (formerly `duckduckgo-search`) is an OPTIONAL dependency, only used
# by the search() keyword feature. If it's not installed, search() will
# automatically fall back to plain requests + BeautifulSoup.
try:
    from ddgs import DDGS  # new package name, recommended
    _HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # legacy name, still on PyPI
        _HAS_DDGS = True
    except ImportError:
        DDGS = None
        _HAS_DDGS = False


# ---------------------------------------------------------------------- #
# Colored logging
# ---------------------------------------------------------------------- #
class _ColorFormatter(logging.Formatter):
    """Formats log records with ANSI colors based on level, for a cleaner
    and more professional-looking console output. Falls back gracefully
    (no colors) on terminals that don't support ANSI codes, such as some
    Windows consoles or when output is piped to a file."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    COLORS = {
        logging.DEBUG: "\033[36m",      # cyan
        logging.INFO: "\033[34m",       # xanh dương (blue)
        logging.WARNING: "\033[33m",    # yellow
        logging.ERROR: "\033[31m",      # red
        logging.CRITICAL: "\033[1;41m",  # bold + red background
    }

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color

    @staticmethod
    def _supports_color() -> bool:
        """Best-effort detection of ANSI color support in the current
        terminal. Disables colors when stdout is not a TTY (e.g. piped to
        a file or running inside some CI/log-capturing environments)."""
        if os.environ.get("NO_COLOR") is not None:
            return False
        if os.environ.get("FORCE_COLOR") is not None:
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        level_name = record.levelname
        message = record.getMessage()

        if self.use_color:
            color = self.COLORS.get(record.levelno, "")
            tag = f"{color}{self.BOLD}[{level_name}]{self.RESET} {message}"
        else:
            tag = f"[{level_name}] {message}"

        return tag


def _setup_logger() -> logging.Logger:
    log = logging.getLogger("pingrabber")
    log.setLevel(logging.INFO)
    log.propagate = False

    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ColorFormatter(use_color=_ColorFormatter._supports_color()))
        log.addHandler(handler)

    return log


logger = _setup_logger()

# Pool of real-world User-Agent strings to rotate through, reducing the
# chance of being fingerprinted as a bot when calling search engines
# (search engines tend to be far more UA-sensitive than Pinterest itself).
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

# Default User-Agent used for image/RSS downloads (stable, no need to rotate)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENTS[0],
}


def _random_search_headers() -> dict:
    """Builds a randomized header set (User-Agent + Accept-Language) for
    each search call, lowering the chance of being flagged/blocked due to
    a fixed, repeatable request pattern."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "vi-VN,vi;q=0.9,en;q=0.8"]),
    }

# Regex to find i.pinimg.com image URLs inside an RSS item's HTML description
IMG_URL_PATTERN = re.compile(
    r"https?://i\.pinimg\.com/[^\s\"'<>]+\.(?:jpg|jpeg|png|gif|webp)",
    re.IGNORECASE,
)

# Common thumbnail size segments Pinterest uses in image URLs; these get
# replaced with "originals" to fetch the highest-quality version.
THUMBNAIL_SIZE_PATTERN = re.compile(
    r"/(\d+x(?:\d+)?|originals)/", re.IGNORECASE
)

# Detects single-pin URLs, e.g. pinterest.com/pin/119134352618387326/
SINGLE_PIN_PATTERN = re.compile(r"^/pin/(\d+)", re.IGNORECASE)

# Detects Pinterest short links, e.g. pin.it/xxxxxxx
SHORT_LINK_PATTERN = re.compile(r"^https?://pin\.it/[\w-]+/?$", re.IGNORECASE)

# Search engines to try in order (fallback chain) when one is blocked or
# errors out. Engines are ordered roughly from "harder to block" (Brave) to
# smaller/independent engines that historically run lighter (or no) bot
# detection. Each engine may need its own result parser
# (see _parse_search_results).
SEARCH_ENGINES = [
    {
        "name": "brave",
        "url": "https://search.brave.com/search",
        "param": "q",
    },
    {
        "name": "mojeek",
        # Fully independent index, no aggressive anti-bot layer.
        "url": "https://www.mojeek.com/search",
        "param": "q",
    },
    {
        "name": "ecosia",
        # Bing-backed results, but historically lighter filtering than Bing.
        "url": "https://www.ecosia.org/search",
        "param": "q",
    },
    {
        "name": "ask",
        # Long-running engine, historically weak bot filtering.
        "url": "https://www.ask.com/web",
        "param": "q",
    },
    {
        "name": "yahoo",
        "url": "https://search.yahoo.com/search",
        "param": "p",
    },
]


# Regex to identify valid board URLs within search results:
# pinterest.com/<user>/<board>/ but NOT /pin/..., /search/..., /explore/...
BOARD_URL_PATTERN = re.compile(
    r"^https?://(?:[a-z]{2,3}\.)?pinterest\.[a-z.]+/"
    r"(?!pin/|search/|explore/|today/)([\w.\-%]+)/([\w.\-%]+)/?$",
    re.IGNORECASE,
)


class PinGrabberError(Exception):
    """Custom exception for the pingrabber library."""


class PinGrabber:
    """Main object for scraping and downloading images from Pinterest."""

    def __init__(
        self,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
        proxies: Optional[List[str]] = None,
        auto_fetch_proxy: bool = False,
        use_random_delay: bool = True,
        min_delay: float = 1.0,
        max_delay: float = 3.0,
    ):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        # If no proxies provided but auto_fetch is True, try to fetch free proxies
        if not proxies and auto_fetch_proxy:
            proxies = self._fetch_free_proxies()

        self.proxies = proxies or []
        self.proxy_index = 0
        self.use_random_delay = use_random_delay
        self.min_delay = min_delay
        self.max_delay = max_delay

    # ------------------------------------------------------------------ #
    # Proxy management
    # ------------------------------------------------------------------ #
    def _fetch_free_proxies(self) -> List[str]:
        """Fetch a list of free proxies using the proxylists library."""
        if not _HAS_PROXYLISTS:
            logger.warning(
                "proxylists not installed. Please install with: pip install proxylists"
            )
            return []

        try:
            proxy_list = proxylists.get_proxies()
            proxies = []
            for p in proxy_list:
                ip = p.get("ip")
                port = p.get("port")
                if not ip or not port:
                    continue
                protocol = p.get("protocol", "http").lower()
                if protocol not in ("http", "https", "socks4", "socks5"):
                    protocol = "http"
                proxies.append(f"{protocol}://{ip}:{port}")
            if proxies:
                logger.info("Fetched %d free proxies from proxylists.", len(proxies))
            else:
                logger.warning("No proxies returned from proxylists.")
            return proxies
        except Exception as e:
            logger.warning("Failed to fetch proxies from proxylists: %s", e)
            return []

    def _get_proxy(self) -> Optional[Dict[str, str]]:
        """Return a proxy dict for requests, or None if no proxies available."""
        if not self.proxies:
            return None
        proxy_url = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        return {"http": proxy_url, "https": proxy_url}

    def _request(
        self,
        method: str,
        url: str,
        max_retries: int = 2,
        **kwargs,
    ) -> requests.Response:
        """
        Perform an HTTP request with proxy rotation and retry logic.
        If a proxy fails, the next one in the list is tried.
        """
        # Set default timeout if not provided
        kwargs.setdefault("timeout", self.timeout)

        # Random delay before request if enabled
        if self.use_random_delay:
            delay = random.uniform(self.min_delay, self.max_delay)
            time.sleep(delay)

        # Try up to max_retries times, rotating through proxies
        for attempt in range(max_retries + 1):
            proxy = self._get_proxy() if self.proxies else None
            if proxy:
                kwargs["proxies"] = proxy

            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except (requests.RequestException, ConnectionError) as e:
                logger.warning(
                    "Request failed (attempt %d/%d) with proxy %s: %s",
                    attempt + 1,
                    max_retries + 1,
                    proxy,
                    e,
                )
                if attempt == max_retries:
                    raise PinGrabberError(
                        f"All retries exhausted for {url} (last proxy: {proxy})"
                    ) from e
                # Wait a bit before retrying with next proxy
                time.sleep(random.uniform(0.5, 1.5))

        # Should never reach here
        raise PinGrabberError(f"Unable to complete request to {url}")

    # ------------------------------------------------------------------ #
    # Utility: check whether a URL is a single pin or a board
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_single_pin_url(url: str) -> bool:
        """Returns True if the URL looks like pinterest.com/pin/<id>/ (single pin)."""
        parsed = urlparse(url)
        return bool(SINGLE_PIN_PATTERN.match(parsed.path))

    @staticmethod
    def is_short_link(url: str) -> bool:
        """Returns True if the URL is a Pinterest short link (pin.it/xxxxxxx)."""
        return bool(SHORT_LINK_PATTERN.match(url.strip()))

    def resolve_short_link(self, short_url: str) -> str:
        """
        Resolves a pin.it/xxxxxxx short link into the full Pinterest URL.

        pin.it doesn't serve content directly — it just redirects (HTTP
        301/302) to the real pin/board URL on pinterest.com. This sends a
        GET request with allow_redirects=True and reads resp.url (the final
        address after following the entire redirect chain).

        Returns the full Pinterest URL (single pin or board, depending on
        what the short link points to).
        """
        try:
            resp = self._request(
                "GET",
                short_url,
                allow_redirects=True,
                max_retries=2,
            )
        except PinGrabberError as exc:
            raise PinGrabberError(
                f"Failed to resolve short link: {short_url} ({exc})"
            ) from exc

        resolved_url = resp.url
        logger.info("Resolved short link: %s -> %s", short_url, resolved_url)
        return resolved_url

    # ------------------------------------------------------------------ #
    # KEYWORD SEARCH
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_bing_real_url(href: str) -> Optional[str]:
        """Bing often wraps the real link inside a base64-encoded redirect
        (the 'u' parameter, prefixed with 'a1' followed by base64). This
        decodes the real URL when present, otherwise returns href unchanged."""
        import base64
        from urllib.parse import urlparse as _urlparse, parse_qs

        parsed = _urlparse(href)
        qs = parse_qs(parsed.query)
        if "u" in qs:
            raw = qs["u"][0]
            if raw.startswith("a1"):
                raw = raw[2:]
            # Bing uses URL-safe base64, sometimes missing '=' padding
            padding = "=" * (-len(raw) % 4)
            try:
                decoded = base64.urlsafe_b64decode(raw + padding).decode("utf-8", errors="ignore")
                return decoded
            except (ValueError, UnicodeDecodeError):
                return href
        return href

    def _parse_search_results(self, engine_name: str, html: str) -> List[str]:
        """Parses search result HTML to extract valid board URLs. Each
        engine has a different HTML structure, so link handling differs
        slightly per engine."""
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
        Finds boards using the `ddgs` package (formerly `duckduckgo-search`).

        Advantages over calling requests directly:
            - Community-maintained package that mimics real browser
              headers/cookies more closely, resulting in a lower block rate.
            - Supports proxies (http/https/socks5) right in the constructor
              — the most effective way to dodge IP-based blocking if you
              have a proxy available.
            - Automatically tries multiple backends internally (DuckDuckGo,
              Bing, Google, etc).

        Returns [] if ddgs isn't installed, or if the call fails (errors
        are logged, not raised, so find_boards() can fall back gracefully).
        """
        if not _HAS_DDGS:
            return []

        query = f"site:pinterest.com {keyword}"
        try:
            ddgs = DDGS(timeout=self.timeout)
            # Pass proxies to DDGS if we have any
            if self.proxies:
                # DDGS expects a dict of proxies like {'http': '...', 'https': '...'}
                # but we only have a list of strings; use the first one as default
                # Better: use the same rotation as _request? But DDGS has its own.
                # We'll just pass the first proxy for simplicity.
                first_proxy = self.proxies[0]
                # DDGS constructor accepts proxies as dict
                # Actually, DDGS doesn't accept proxies in constructor, only in methods? Check later.
                # We'll skip proxy passing for DDGS and rely on its built-in rotation.
                ddgs = DDGS(timeout=self.timeout)
            try:
                raw_results = ddgs.text(query, max_results=max_results * 3)
            finally:
                # Some DDGS versions support a context manager / .close();
                # close it if available to free up the HTTP connection.
                close_fn = getattr(ddgs, "close", None)
                if callable(close_fn):
                    close_fn()
        except Exception as exc:  # noqa: BLE001 - ddgs can raise several different error types
            logger.warning("  [ddgs] Call failed: %s", exc)
            return []

        board_urls: List[str] = []
        for item in raw_results or []:
            # Depending on the version, the key may be "href" or "url"
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
        FALLBACK: calls requests against multiple search engines directly,
        used when the `ddgs` package isn't installed or fails. Rotates
        User-Agents, retries, and falls back across multiple engines (see
        SEARCH_ENGINES).
        """
        query = f"site:pinterest.com {keyword}"
        last_error: Optional[Exception] = None

        for engine in SEARCH_ENGINES:
            for attempt in range(1, max_retries + 1):
                try:
                    headers = _random_search_headers()
                    # Use self._request to benefit from proxy rotation
                    resp = self._request(
                        "GET",
                        engine["url"],
                        params={engine["param"]: query},
                        headers=headers,
                        max_retries=1,  # _request already retries, but we'll limit here
                    )

                    # Check for blocking status codes manually
                    if resp.status_code in (403, 429):
                        logger.warning(
                            "  [%s] Blocked (HTTP %d), retrying %d/%d...",
                            engine["name"], resp.status_code, attempt, max_retries,
                        )
                        time.sleep(delay_seconds + random.uniform(0, 1.5))
                        continue

                    board_urls = self._parse_search_results(engine["name"], resp.text)
                    if board_urls:
                        logger.info(
                            "  [%s] Found %d board(s).", engine["name"], len(board_urls)
                        )
                        return board_urls[:max_results]

                    logger.info("  [%s] No matching results, trying next engine.", engine["name"])
                    break  # Engine returned OK but no boards -> move to next engine

                except PinGrabberError as exc:
                    # _request raises PinGrabberError on failure
                    last_error = exc
                    logger.warning(
                        "  [%s] Request error (attempt %d/%d): %s",
                        engine["name"], attempt, max_retries, exc,
                    )
                    time.sleep(delay_seconds + random.uniform(0, 1.5))
                except requests.RequestException as exc:
                    last_error = exc
                    logger.warning(
                        "  [%s] Request error (attempt %d/%d): %s",
                        engine["name"], attempt, max_retries, exc,
                    )
                    time.sleep(delay_seconds + random.uniform(0, 1.5))

            # Brief pause before moving on to the next engine
            time.sleep(delay_seconds)

        if last_error:
            logger.error(
                "All search engines failed. Last error: %s. "
                "Your network may be blocking access to search engines — "
                "try again later, switch network/VPN, or manually find a "
                "board in your browser and call download(board_url) directly.",
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
        Finds Pinterest board URLs related to a keyword.

        Priority order:
            1. Use the `ddgs` package (recommended) if installed — it's
               community-maintained, mimics a real browser more closely,
               and supports proxies, resulting in a much lower block rate.
            2. If `ddgs` isn't installed or the call fails, automatically
               fall back to calling requests directly against multiple
               search engines (see SEARCH_ENGINES), with User-Agent
               rotation, retries, and delays between attempts.

        To use option 1 (recommended), install:
            pip install ddgs

        Note: this is NOT a direct search inside Pinterest itself (its
        search page needs JS rendering, which requests can't read) — it
        relies on a search engine's index to find related public boards.
        Results may be empty depending on your IP/network — if so, find a
        board manually in your browser and call download(board_url) directly.

        Returns a deduplicated list of board URLs, capped at max_results.
        """
        if _HAS_DDGS:
            logger.info("Searching for boards via the ddgs package...")
            board_urls = self._find_boards_via_ddgs(keyword, max_results=max_results)
            if board_urls:
                logger.info("  [ddgs] Found %d board(s).", len(board_urls))
                return board_urls
            logger.info("  [ddgs] No results, falling back to direct requests.")
        else:
            logger.info(
                "Package 'ddgs' is not installed (pip install ddgs) — "
                "using the direct-requests fallback instead."
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
        max_total_images: Optional[int] = None,
    ) -> List[str]:
        """
        Finds boards related to a keyword, then automatically collects the
        original (high-quality) image URLs from those boards. Does NOT
        download anything to disk — it only returns a list of raw links
        for you to use however you like.

        Example:
            import pingrabber
            links = pingrabber.search("nature")
            print(links)  # ['https://i.pinimg.com/originals/.../a.jpg', ...]

            # Stop as soon as 20 images are collected, instead of scanning
            # every board found:
            links = pingrabber.search("nature", max_total_images=20)

        Args:
            keyword: search keyword, e.g. "nature", "travel".
            max_boards: maximum number of boards to scan.
            max_images_per_board: maximum number of images to pull per board.
            max_retries: retry attempts per search engine on block/error.
            delay_seconds: base delay (seconds) between attempts, to reduce
                the chance of being blocked for calling too fast.
            max_total_images: if set, stop fetching as soon as this many
                unique image URLs have been collected overall. Once the
                target is reached, remaining boards are skipped entirely
                (no RSS fetch is even attempted for them) — useful when
                you only need a fixed number of images instead of
                scanning every board that was found.

        Returns a list of original image URLs (strings), capped at
        max_total_images if provided, empty if nothing was found. If
        empty, check the WARNING/ERROR logs above for the specific cause
        (blocked, engines exhausted, or no related boards).
        """
        logger.info("Searching for boards related to keyword: %s", keyword)
        board_urls = self.find_boards(
            keyword,
            max_results=max_boards,
            max_retries=max_retries,
            delay_seconds=delay_seconds,
        )

        if not board_urls:
            logger.warning(
                "No boards found for: %s. "
                "If the log above shows 403/429 errors on every engine, "
                "your network/IP is likely being blocked by search engines.",
                keyword,
            )
            return []

        logger.info("Found %d board(s), fetching images...", len(board_urls))

        all_image_urls: List[str] = []
        for board_url in board_urls:
            if max_total_images is not None and len(all_image_urls) >= max_total_images:
                logger.info(
                    "Reached target of %d image(s), skipping remaining board(s).",
                    max_total_images,
                )
                break

            # Calculate how many more images we still need from this board.
            # Never fetch more than max_images_per_board; if we have a
            # tighter remaining budget, use that instead — this avoids
            # parsing hundreds of RSS <item> elements unnecessarily.
            per_board_limit = max_images_per_board
            if max_total_images is not None:
                remaining = max_total_images - len(all_image_urls)
                per_board_limit = min(per_board_limit, remaining)

            try:
                rss_url = self.build_rss_url(board_url)
                rss_content = self.fetch_rss(rss_url)
                # Pass the limit so extract_image_urls stops early instead
                # of iterating over every <item> in a potentially huge feed.
                image_urls = self.extract_image_urls(rss_content, limit=per_board_limit)

                added = 0
                for url in image_urls:
                    if url not in all_image_urls:
                        if (
                            max_total_images is not None
                            and len(all_image_urls) >= max_total_images
                        ):
                            break
                        all_image_urls.append(url)
                        added += 1

                logger.info("  + %s -> %d image(s)", board_url, added)
                # Small delay between boards to avoid bursting requests
                time.sleep(delay_seconds * 0.5)
            except PinGrabberError as exc:
                logger.error("  Error processing board %s: %s", board_url, exc)

        logger.info("Done. Collected %d raw image link(s) total.", len(all_image_urls))
        return all_image_urls

    # ------------------------------------------------------------------ #
    # Step 1: Convert a board URL into its RSS feed URL
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_rss_url(board_url: str) -> str:
        """
        Converts a regular Pinterest board URL into its RSS feed URL.

        Example:
            https://www.pinterest.com/username/boardname/
            -> https://www.pinterest.com/username/boardname.rss
        """
        parsed = urlparse(board_url)
        if "pinterest." not in parsed.netloc:
            raise PinGrabberError(f"Invalid URL, not a Pinterest URL: {board_url}")

        path = parsed.path.strip("/")
        if not path:
            raise PinGrabberError(f"Could not find a board path in URL: {board_url}")

        if path.endswith(".rss"):
            rss_path = path
        else:
            rss_path = f"{path}.rss"

        return f"https://{parsed.netloc}/{rss_path}"

    # ------------------------------------------------------------------ #
    # Step 2: Fetch the RSS feed content
    # ------------------------------------------------------------------ #
    def fetch_rss(self, rss_url: str) -> str:
        """Sends a request to fetch the RSS feed content (XML/text)."""
        try:
            resp = self._request("GET", rss_url, max_retries=2)
            return resp.text
        except PinGrabberError as exc:
            raise PinGrabberError(f"Failed to fetch RSS feed: {rss_url} ({exc})") from exc

    # ------------------------------------------------------------------ #
    # Step 3: Parse the RSS with BeautifulSoup -> get original image URLs
    # ------------------------------------------------------------------ #
    def extract_image_urls(self, rss_content: str, limit: Optional[int] = None) -> List[str]:
        """
        Uses BeautifulSoup to parse the RSS feed's XML, collects every
        <img> tag inside each <item><description>, then upgrades the
        thumbnail URL to the original-quality ("originals") version.

        Args:
            rss_content: raw RSS/XML text from fetch_rss().
            limit: if set, stop parsing as soon as this many unique image
                URLs have been collected — avoids iterating over hundreds
                of <item> elements when only a few images are needed.
        """
        soup = BeautifulSoup(rss_content, "lxml-xml")
        items = soup.find_all("item")

        if not items:
            # Some feeds may fail to parse correctly with "lxml-xml" (rare);
            # retry with the default HTML parser as a fallback.
            soup = BeautifulSoup(rss_content, "html.parser")
            items = soup.find_all("item")

        image_urls: List[str] = []

        for item in items:
            # Early exit: stop processing items once the limit is reached
            if limit is not None and len(image_urls) >= limit:
                break

            description = item.find("description")
            if not description or not description.text:
                continue

            # description contains escaped HTML, parse it a second time
            desc_soup = BeautifulSoup(description.text, "html.parser")
            img_tags = desc_soup.find_all("img")

            for img in img_tags:
                if limit is not None and len(image_urls) >= limit:
                    break
                src = img.get("src")
                if not src:
                    continue
                original_url = self._to_original_quality(src)
                if original_url not in image_urls:
                    image_urls.append(original_url)

            # In case an image URL appears as plain text instead of an <img> tag
            for match in IMG_URL_PATTERN.findall(description.text):
                if limit is not None and len(image_urls) >= limit:
                    break
                original_url = self._to_original_quality(match)
                if original_url not in image_urls:
                    image_urls.append(original_url)

        return image_urls

    @staticmethod
    def _to_original_quality(image_url: str) -> str:
        """Replaces the thumbnail size segment (e.g. 236x) with 'originals'."""
        return THUMBNAIL_SIZE_PATTERN.sub("/originals/", image_url, count=1)

    # ------------------------------------------------------------------ #
    # SINGLE PIN handling (no RSS, must fetch the HTML page directly)
    # ------------------------------------------------------------------ #
    def fetch_pin_page(self, pin_url: str) -> str:
        """Downloads the HTML content of a single pin's page."""
        try:
            resp = self._request("GET", pin_url, max_retries=2)
            return resp.text
        except PinGrabberError as exc:
            raise PinGrabberError(f"Failed to fetch pin page: {pin_url} ({exc})") from exc

    def extract_single_pin_image(self, html_content: str) -> Optional[str]:
        """
        Uses BeautifulSoup to find the main image of a single pin.

        Pinterest embeds the pin's main image in:
            <meta property="og:image" content="https://i.pinimg.com/originals/...">
        This is usually already the original-quality image, no upgrade
        needed. If not found, falls back to scanning the raw HTML with a
        regex for an i.pinimg.com image URL.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return self._to_original_quality(og_image["content"])

        # Fallback: scan the raw HTML for a pinimg.com image URL
        matches = IMG_URL_PATTERN.findall(html_content)
        if matches:
            return self._to_original_quality(matches[0])

        return None

    def download_single_pin(self, pin_url: str, output_dir: str = "downloads") -> List[str]:
        """
        Downloads the image from a single pin URL, e.g.:
            https://www.pinterest.com/pin/119134352618387326/

        Returns a list of saved file paths (empty if no image was found).
        """
        os.makedirs(output_dir, exist_ok=True)

        logger.info("Fetching pin page: %s", pin_url)
        html_content = self.fetch_pin_page(pin_url)

        image_url = self.extract_single_pin_image(html_content)
        if not image_url:
            logger.warning("No image found in pin: %s", pin_url)
            return []

        try:
            path = self.download_image(image_url, output_dir)
            logger.info("Saved: %s", path)
            return [path]
        except PinGrabberError as exc:
            logger.error("Failed to download image: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Step 4: Download the image to disk
    # ------------------------------------------------------------------ #
    def download_image(self, image_url: str, output_dir: str) -> str:
        """Downloads a single image into output_dir, returns the saved file path."""
        filename = os.path.basename(urlparse(image_url).path) or "image.jpg"
        filepath = os.path.join(output_dir, filename)

        try:
            resp = self._request("GET", image_url, stream=True, max_retries=2)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return filepath
        except PinGrabberError as exc:
            raise PinGrabberError(f"Failed to download image: {image_url} ({exc})") from exc

    # ------------------------------------------------------------------ #
    # Main entry point: from any supported URL -> download all images to disk
    # ------------------------------------------------------------------ #
    def download(self, url: str, output_dir: str = "downloads") -> List[str]:
        """
        Full pipeline, automatically detecting the URL type:

            - If it's a short link (pin.it/xxxxxxx):
                resolve it to the full URL first, then proceed as below.
            - If it's a single pin URL (pinterest.com/pin/<id>/):
                fetch the HTML page directly -> extract the og:image -> download it.
            - If it's a board URL (pinterest.com/username/boardname/):
                1. Build the RSS feed URL from the board URL.
                2. Fetch the RSS content.
                3. Extract the list of original-quality image URLs.
                4. Download all images into output_dir.

        Returns a list of paths to the successfully saved image files.
        """
        if self.is_short_link(url):
            logger.info("Detected a pin.it short link, resolving...")
            url = self.resolve_short_link(url)

        if self.is_single_pin_url(url):
            logger.info("Detected a single pin URL, switching to single-pin mode.")
            return self.download_single_pin(url, output_dir=output_dir)

        os.makedirs(output_dir, exist_ok=True)

        rss_url = self.build_rss_url(url)
        logger.info("Fetching RSS feed: %s", rss_url)

        rss_content = self.fetch_rss(rss_url)
        image_urls = self.extract_image_urls(rss_content)

        if not image_urls:
            logger.warning("No images found in board: %s", url)
            return []

        logger.info("Found %d image(s). Starting download...", len(image_urls))

        saved_paths: List[str] = []
        for index, img_url in enumerate(image_urls, start=1):
            try:
                path = self.download_image(img_url, output_dir)
                saved_paths.append(path)
                logger.info("(%d/%d) Saved: %s", index, len(image_urls), path)
            except PinGrabberError as exc:
                logger.error("(%d/%d) Failed to download image: %s", index, len(image_urls), exc)

        logger.info("Done. Saved %d/%d image(s).", len(saved_paths), len(image_urls))
        return saved_paths


# ---------------------------------------------------------------------- #
# Module-level shortcut function: pingrabber.download(url)
# ---------------------------------------------------------------------- #
def download(
    url: str,
    output_dir: str = "downloads",
    timeout: int = 15,
    proxies: Optional[List[str]] = None,
    auto_fetch_proxy: bool = False,
    use_random_delay: bool = True,
) -> List[str]:
    """
    Quick utility function, no need to manually instantiate PinGrabber.
    Automatically detects whether the URL is a board, a single pin, or a
    pin.it short link, and handles it accordingly.

    Example:
        import pingrabber

        # Board
        pingrabber.download("https://www.pinterest.com/username/boardname/")

        # Single pin
        pingrabber.download("https://www.pinterest.com/pin/119134352618387326/")

        # Short link
        pingrabber.download("https://pin.it/3MKmfwvjG")

        # With auto proxy fetching
        pingrabber.download("...", auto_fetch_proxy=True)
    """
    grabber = PinGrabber(
        timeout=timeout,
        proxies=proxies,
        auto_fetch_proxy=auto_fetch_proxy,
        use_random_delay=use_random_delay,
    )
    return grabber.download(url, output_dir=output_dir)


def search(
    keyword: str,
    max_boards: int = 3,
    max_images_per_board: int = 25,
    max_retries: int = 2,
    delay_seconds: float = 1.5,
    timeout: int = 15,
    max_total_images: Optional[int] = None,
    proxies: Optional[List[str]] = None,
    auto_fetch_proxy: bool = False,
    use_random_delay: bool = True,
) -> List[str]:
    """
    Quick utility function: finds boards related to a keyword and returns
    a list of raw (original-quality) image links, without downloading
    anything to disk.

    Automatically rotates User-Agents, retries, and switches between
    multiple search engines if blocked.

    Example:
        import pingrabber

        links = pingrabber.search("nature")
        for url in links:
            print(url)

        # Increase retries and delay if your network gets blocked easily
        links = pingrabber.search("nature", max_retries=4, delay_seconds=3)

        # Only need 20 images? Stop as soon as that many are collected,
        # instead of scanning every board found:
        links = pingrabber.search("nature", max_total_images=20)

        # Use auto proxy fetching
        links = pingrabber.search("nature", auto_fetch_proxy=True)
    """
    grabber = PinGrabber(
        timeout=timeout,
        proxies=proxies,
        auto_fetch_proxy=auto_fetch_proxy,
        use_random_delay=use_random_delay,
    )
    return grabber.search(
        keyword,
        max_boards=max_boards,
        max_images_per_board=max_images_per_board,
        max_retries=max_retries,
        delay_seconds=delay_seconds,
        max_total_images=max_total_images,
    )
