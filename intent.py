"""Small deterministic intent router. No AI, external calls or personal profiling."""

SUBJECT_HINTS = (
    ("nmt", ("нмт", "nmt", "зно", "zno")),
    ("en", ("англ", "english", "english tutor")),
    ("de", ("німець", "немец", "deutsch", "german")),
    ("math", ("матем", "алгеб", "геометр", "math")),
    ("history", ("істор", "истор", "history")),
    ("code", ("програм", "python", "роблокс", "roblox", "javascript", "coding")),
)


def infer_subject(text: str) -> str | None:
    """Return a subject code for common Ukrainian/Russian/English phrases."""
    normalized = text.casefold()
    for subject, stems in SUBJECT_HINTS:
        if any(stem in normalized for stem in stems):
            return subject
    return None


def looks_like_tutor_request(text: str) -> bool:
    normalized = text.casefold()
    return any(part in normalized for part in ("репетитор", "викладач", "tutor", "уроки", "заняття"))
