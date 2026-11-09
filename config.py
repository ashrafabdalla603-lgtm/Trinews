import os


def _e(key, default=""):
    return os.getenv(key) or default   # GitHub passes unset variables as "", so use "or"


BRAND = _e("BRAND_NAME", "Tri News")
HANDLE = _e("BRAND_HANDLE", "@trinews")          # confirm the handle is free on Instagram
TAG = _e("BRAND_TAG", "TriNews")
PARENT = _e("PARENT_NAME", "TriBridge Services")
BG = _e("BRAND_BG", "#0A2A1F")
ACCENT = _e("BRAND_ACCENT", "#FF5A36")
MODEL = _e("ANTHROPIC_MODEL", "claude-sonnet-5-5")
