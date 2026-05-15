"""Tests for the conversational contact-collection flow."""

from __future__ import annotations

import pytest

from src.contact import Contact, format_missing, parse_contact
from src.memory import memory


@pytest.fixture(autouse=True)
def _wipe_memory():
    memory.reset()
    yield
    memory.reset()


# -------------------- parse_contact ------------------------------------------


def test_parse_full_english_line():
    c = parse_contact("Ahmed Mohamed, 01012345678, ahmed@example.com")
    assert c.phone == "01012345678"
    assert c.email == "ahmed@example.com"
    assert c.name and "Ahmed" in c.name
    assert c.is_actionable()


def test_parse_phone_only():
    c = parse_contact("0100 123 4567 0100 123 4567 01098765432")
    assert c.phone == "01098765432"
    assert c.is_actionable()


def test_parse_email_only():
    c = parse_contact("just-call-me@niletel.com")
    assert c.email == "just-call-me@niletel.com"
    assert c.phone is None
    assert c.is_actionable()


def test_parse_arabic_with_label():
    c = parse_contact("اسمي محمد علي والهاتف 01098765432")
    assert c.phone == "01098765432"
    # Name capture is best-effort; we just want the leftover to be non-junk.
    assert c.name is not None


def test_parse_garbage_is_not_actionable():
    c = parse_contact("yes please thanks")
    assert not c.is_actionable()


def test_format_missing_lists_only_what_is_missing():
    assert format_missing(Contact()) == "name, phone or email"
    assert format_missing(Contact(phone="01012345678")) == "name"
    assert (
        format_missing(Contact(name="Ahmed"))
        == "phone or email"
    )
    assert format_missing(Contact(name="Ahmed", phone="01012345678")) == ""


# -------------------- ConversationMemory slots -------------------------------


def test_memory_pending_complaint_roundtrip():
    memory.set_pending_complaint("s1", "internet is down")
    assert memory.get_pending_complaint("s1") == "internet is down"
    memory.clear_pending_complaint("s1")
    assert memory.get_pending_complaint("s1") is None


def test_memory_contact_roundtrip():
    memory.set_contact("s1", {"name": "Ahmed", "phone": "01012345678"})
    stored = memory.get_contact("s1")
    assert stored == {"name": "Ahmed", "phone": "01012345678"}
    # mutation safety
    stored["phone"] = "0"
    assert memory.get_contact("s1")["phone"] == "01012345678"


def test_clear_session_drops_pending_and_contact():
    memory.append("s1", "user", "hi")
    memory.set_pending_complaint("s1", "broken")
    memory.set_contact("s1", {"email": "a@b.co"})
    assert memory.clear("s1") is True
    assert memory.get_pending_complaint("s1") is None
    assert memory.get_contact("s1") is None
