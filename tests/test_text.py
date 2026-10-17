from datetime import datetime, timedelta, timezone

from hirejutsu.text import clean, html_to_text, parse_date

UTC = timezone.utc


def test_html_to_text_keeps_paragraphs_and_lists():
    html = "<h2>About</h2><p>We build <b>tools</b>.</p><ul><li>Python</li><li>SQL</li></ul>"
    assert html_to_text(html) == "About\nWe build tools.\n- Python\n- SQL"


def test_html_to_text_handles_escaped_html():
    assert html_to_text("&lt;p&gt;Fish &amp;amp; chips&lt;/p&gt;") == "Fish & chips"


def test_html_to_text_drops_scripts_and_styles():
    assert html_to_text("<style>p {}</style><p>Hi</p><script>x()</script>") == "Hi"


def test_html_to_text_line_breaks():
    assert html_to_text("one<br>two<br/>three") == "one\ntwo\nthree"


def test_html_to_text_empty():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_clean_collapses_whitespace():
    assert clean("  a \t b\n\n c  ") == "a b c"
    assert clean(None) == ""


def test_parse_date_iso_with_z():
    assert parse_date("2026-10-15T12:30:00Z") == datetime(2026, 10, 15, 12, 30, tzinfo=UTC)


def test_parse_date_iso_with_offset():
    assert parse_date("2026-10-15T18:00:00+05:30") == datetime(2026, 10, 15, 12, 30, tzinfo=UTC)


def test_parse_date_iso_with_fraction():
    assert parse_date("2026-10-15T12:30:00.123Z") == datetime(2026, 10, 15, 12, 30, 0, 123000, tzinfo=UTC)


def test_parse_date_plain_date():
    assert parse_date("2026-10-15") == datetime(2026, 10, 15, tzinfo=UTC)


def test_parse_date_naive_is_utc():
    assert parse_date("2026-10-15 12:30:00") == datetime(2026, 10, 15, 12, 30, tzinfo=UTC)


def test_parse_date_epoch_seconds_and_millis():
    expected = datetime(2026, 10, 15, 12, 30, tzinfo=UTC)
    assert parse_date(int(expected.timestamp())) == expected
    assert parse_date(int(expected.timestamp() * 1000)) == expected
    assert parse_date(str(int(expected.timestamp()))) == expected


def test_parse_date_rfc_2822():
    assert parse_date("Thu, 15 Oct 2026 12:30:00 +0000") == datetime(2026, 10, 15, 12, 30, tzinfo=UTC)


def test_parse_date_datetime_passthrough():
    local = datetime(2026, 10, 15, 18, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert parse_date(local) == datetime(2026, 10, 15, 12, 30, tzinfo=UTC)


def test_parse_date_garbage():
    assert parse_date("soon") is None
    assert parse_date("") is None
    assert parse_date(None) is None
