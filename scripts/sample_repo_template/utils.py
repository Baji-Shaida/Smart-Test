"""Small general purpose helpers."""
import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def slugify(text):
    """Convert text to a lowercase URL slug: words joined by single hyphens.

    Non alphanumeric characters are removed, e.g. "Hello, World!" -> "hello-world".
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words)


def is_valid_email(email):
    """Return True if email looks like a valid address (name@domain.tld), else False."""
    if not isinstance(email, str):
        return False
    return bool(EMAIL_RE.match(email.strip()))


def chunk_list(items, size):
    """Split items into consecutive lists of length size.

    The last chunk may be shorter if len(items) is not a multiple of size.
    Raises ValueError if size is not positive.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    end = len(items) - len(items) % size
    return [items[i:i + size] for i in range(0, end, size)]
