from backend.dcif.parse_html import parse_html_sections


def test_parse_html_sections_keeps_headings_and_body_text() -> None:
    html = b"""
    <html>
      <head><title>DCIF</title><script>ignore()</script></head>
      <body>
        <nav>Navigation</nav>
        <h1>Training</h1>
        <p>Users must complete training before instrument access.</p>
        <h2>NMR</h2>
        <p>The facility hosts NMR instrumentation.</p>
      </body>
    </html>
    """

    title, sections = parse_html_sections(html)

    assert title == "Training"
    assert [section.heading for section in sections] == ["Training", "NMR"]
    assert "Navigation" not in "\n".join(section.text for section in sections)
    assert "instrument access" in sections[0].text
