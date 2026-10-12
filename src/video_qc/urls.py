"""URL classification. Domain syntax + maintained public suffix data via tldextract."""

import re

import tldextract

# Bundled snapshot: offline, deterministic, no downloads during a job.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)
_candidate = re.compile(
    r"(?i)(?<![\w@])(?:https?://|www\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+(?:[:][0-9]{1,5})?(?:[/][^\s<>]*)?"
)


def find_urls(text: str) -> list[str]:
    # OCR often inserts whitespace around URL punctuation.
    text = re.sub(r"\s*([.:/])\s*", r"\1", text)
    found = []
    for match in _candidate.finditer(text):
        value = match.group().rstrip(".,;:!?)]}")
        parts = _extract(value)
        explicit = re.match(r"(?i)^(?:https?://|w{3,4}\.)", value)
        if parts.domain and (parts.suffix or explicit) and not parts.domain.isdigit():
            found.append(value)
    return found
