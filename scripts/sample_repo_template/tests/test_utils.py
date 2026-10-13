from utils import is_valid_email, slugify


def test_slugify_basic():
    assert slugify("Hello, World!") == "hello-world"


def test_is_valid_email():
    assert is_valid_email("jane@example.com") is True
    assert is_valid_email("not-an-email") is False
    assert is_valid_email(None) is False
