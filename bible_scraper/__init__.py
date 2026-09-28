"""Bible parallel-corpus collector: THADBSI (Thadou Kuki) <-> NIV (English).

Acquires publicly accessible chapter text from bible.com with Playwright,
extracts verse-level text keyed by canonical Bible references, aligns the
two versions by reference, and verifies/audits the result.

Nothing in this package translates, rewrites, or invents source text.
"""

__version__ = "1.0.0"
SCRAPER_VERSION = __version__
