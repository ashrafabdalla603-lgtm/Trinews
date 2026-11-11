"""Rule-based priority. Claude may nudge the result by +/-10 afterwards.
Tri News is gossip and daily-life first. Official alerts (exams, tax, portals) are kept, but they rank
below entertainment unless a deadline is close."""
import re
import datetime as dt

# (label, base score, regex). The highest matching base wins.
TOPICS = [
    # gossip, entertainment and daily life
    ("CELEBRITY", 84, r"celebrit|\bcelebs?\b|gossip|baby mama|baby daddy|breakup|wedding|big day|influencer|\bactor\b|actress|\bhosted\b|\bbash\b"),
    ("MUSIC", 82, r"\bsong\b|album|\bep\b|concert|\bgig\b|\btour\b|artiste|musician|rapper|singer|gengetone|bongo|amapiano|gospel|\bdj\b|music video"),
    ("VIRAL", 82, r"viral|trending|tiktok|youtuber|tiktoker|\bmeme|challenge|netizens|\bx users\b|backlash|outrage"),
    ("RELATIONSHIPS", 78, r"cheat|divorce|marries|engaged|pregnan|\bex-(wife|husband|girlfriend|boyfriend)|lover|couple|girlfriend|boyfriend|dating"),
    ("SCREEN", 76, r"movie|\bfilm\b|series|netflix|showmax|\btv show\b|premiere|box office|reality show|drama|interview|podcast"),
    ("COMEDY", 74, r"comedian|\bskit\b|stand-?up|comedy"),
    ("HOT-TOPIC", 70, r"controvers|\brow\b|clash|petition|\bbanned?\b|\bbill\b|jailed|sentenced|arrested|charged"),
    ("LIFESTYLE", 66, r"fashion|\bstyle\b|\bfood\b|recipe|travel|festival|nightlife|relationship|fitness|wellness"),
    ("TECH-SCIENCE", 56, r"\bscience\b|\bspace\b|\btech\b|\bai\b|gadget|invention|discovery|robot|\bnasa\b"),
    ("MONEY-CAREER", 56, r"side hustle|savings|invest|budget|career|internship|\bjobs?\b|salary|scholarship|bursary"),
    ("EDUCATION", 50, r"school|universit|college|student|teacher|\bcbc\b"),
    ("GOVERNMENT", 40, r"gazette|public service|ministry|county government|cabinet secretary"),
    # official alerts: kept, but they rank below gossip unless a deadline is close
    ("KCSE", 62, r"\bkcse\b"),
    ("KUCCPS", 62, r"kuccps|university placement|revis(e|ion) of (courses|choices)"),
    ("HELB", 60, r"\bhelb\b|higher education loans"),
    ("KNEC", 58, r"\bknec\b|\bkjsea\b|\bkpsea\b|\bkcpe\b"),
    ("KRA", 58, r"\bkra\b|i-?tax|tax returns?|kra pin"),
    ("PORTAL", 55, r"portal|e-?citizen|\bsha\b|social health authority|online (application|registration)|applications? (are )?(now )?(open|close)"),
    ("GOV-SERVICES", 50, r"\btsc\b|\bntsa\b|immigration|passport|huduma|driving licen[cs]e|national id"),
]
ALERTS = {"KCSE", "KUCCPS", "HELB", "KNEC", "KRA", "PORTAL", "GOV-SERVICES"}
DEADLINE = r"deadline|closes|closing|last day|ends (on|today|tomorrow)|now open|opens (today|tomorrow|on)"
FRESH = r"last night|yesterday|just in|breaking|this morning|trending now|minutes ago|hours ago"
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
    if topic in ALERTS and re.search(DEADLINE, t):
        s += 14
    if re.search(FRESH, t):
        s += 8
    if re.search(EDU, t):
        s += 12                               # edutainment bonus: a learning angle
    if published:
        age = dt.datetime.now(dt.timezone.utc) - published
        if age < dt.timedelta(hours=2):
            s += 5
        elif age > dt.timedelta(hours=12):
            s -= 10                           # stale news sinks
        elif age > dt.timedelta(hours=6):
            s -= 5
    s += {5: 5, 4: 2, 2: -5, 1: -10}.get(trust, 0)
    hint = "speculation" if re.search(SPEC, t) else ("confirmed" if trust >= 5 else "unverified")
    return max(0, min(100, s)), topic, hint
