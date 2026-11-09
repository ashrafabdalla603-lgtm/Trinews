"""Rule-based priority. Claude may nudge the result by +/-10 afterwards.
Deadline alerts stay on top because a missed deadline hurts people. Everything else is
weighted toward entertainment, and anything with a learning angle gets an edutainment bonus."""
import re
import datetime as dt

# (label, base score, regex). The highest matching base wins.
TOPICS = [
    # urgent public alerts
    ("KCSE", 90, r"\bkcse\b"),
    ("KUCCPS", 90, r"kuccps|university placement|revis(e|ion) of (courses|choices)"),
    ("HELB", 88, r"\bhelb\b|higher education loans"),
    ("KNEC", 86, r"\bknec\b|\bkjsea\b|\bkpsea\b|\bkcpe\b"),
    ("KRA", 85, r"\bkra\b|i-?tax|tax returns?|kra pin"),
    ("PORTAL", 82, r"portal|e-?citizen|\bsha\b|social health authority|online (application|registration)|applications? (are )?(now )?(open|close)"),
    ("GOV-SERVICES", 70, r"\btsc\b|\bntsa\b|immigration|passport|huduma|driving licen[cs]e|national id"),
    # entertainment first
    ("CELEBRITY", 58, r"celebrit|\bcelebs?\b|gossip|baby mama|baby daddy|breakup|wedding|dating|influencer|\bactor\b|actress"),
    ("MUSIC", 58, r"\bsong\b|album|\bep\b|concert|\bgig\b|\btour\b|artiste|musician|rapper|singer|gengetone|bongo|amapiano|gospel|\bdj\b|music video"),
    ("VIRAL", 58, r"viral|trending|tiktok|youtuber|tiktoker|\bmeme|challenge|netizens|\bx users\b"),
    ("SCREEN", 55, r"movie|\bfilm\b|series|netflix|showmax|\btv show\b|premiere|box office|reality show|drama"),
    ("COMEDY", 52, r"comedian|\bskit\b|stand-?up|comedy"),
    ("LIFESTYLE", 48, r"fashion|\bstyle\b|\bfood\b|recipe|travel|festival|nightlife|relationship|fitness|wellness"),
    # edutainment-friendly beats
    ("TECH-SCIENCE", 50, r"\bscience\b|\bspace\b|\btech\b|\bai\b|gadget|invention|discovery|robot|\bnasa\b"),
    ("MONEY-CAREER", 50, r"side hustle|savings|invest|budget|career|internship|\bjobs?\b|salary|scholarship|bursary"),
    ("EDUCATION", 45, r"school|universit|college|student|teacher|\bcbc\b"),
    ("GOVERNMENT", 40, r"gazette|public service|ministry|county government|cabinet secretary"),
]
URGENT = r"deadline|closes|closing|last day|ends (on|today|tomorrow)|now open|opens (today|tomorrow|on)|opening|today|tomorrow|this week|released|release date"
EDU = r"explained|how to|\bwhy\b|what is|did you know|\bfacts?\b|history of|\bstudy\b|research|\btips\b|guide|\blearn|myth|truth about|simple steps|what it means"
SPEC = r"reportedly|rumou?r|allegedly|alleged|sources say|speculat|insiders|unconfirmed|netizens"


def score(text, trust=3, published=None):
    """Returns (score 0-100, topic label, claim hint)."""
    t = text.lower()
    topic, base = "OTHER", 0
    for label, pts, rx in TOPICS:
        if pts > base and re.search(rx, t):
            topic, base = label, pts
    if base == 0:
        return 0, topic, "unverified"
    s = base
    if re.search(URGENT, t):
        s += 10
    if re.search(EDU, t):
        s += 12                               # edutainment bonus: a learning angle
    if published and dt.datetime.now(dt.timezone.utc) - published < dt.timedelta(hours=2):
        s += 5
    s += {5: 5, 4: 2, 2: -5, 1: -10}.get(trust, 0)
    hint = "speculation" if re.search(SPEC, t) else ("confirmed" if trust >= 5 else "unverified")
    return max(0, min(100, s)), topic, hint
