from pydantic import HttpUrl

from backend.dcif.crawl import canonical_url, document_type_for, extract_links, normalize_download_url, should_fetch_url
from backend.dcif.models import CrawlConfig


def test_crawl_scope_keeps_seed_page_and_direct_pdf_links_only() -> None:
    config = CrawlConfig(
        allowed_domains=["chemistry.mit.edu"],
        root_urls=[
            HttpUrl(
                "https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/"
            )
        ],
        follow_html_links=False,
        fetch_linked_files=True,
        linked_file_extensions=[".pdf"],
    )
    root_urls = {canonical_url(str(url)) for url in config.root_urls}

    assert should_fetch_url(
        "https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/",
        root_urls=root_urls,
        config=config,
    )
    assert not should_fetch_url(
        "https://chemistry.mit.edu/facilities-and-centers/department-of-chemistry-instrumentation-facility-dcif/dcif-training-request-form/",
        root_urls=root_urls,
        config=config,
    )
    assert should_fetch_url(
        "https://www.dropbox.com/s/gpgpwnet56fst6t/Single%20Q%20LCMS_quick%20guide.pdf?dl=1",
        root_urls=root_urls,
        config=config,
    )
    assert should_fetch_url(
        "https://chemistry.mit.edu/wp-content/uploads/2019/08/DCIF_Double_echo_filter.pdf",
        root_urls=root_urls,
        config=config,
    )
    assert not should_fetch_url("https://chemistry.mit.edu/faculty/", root_urls=root_urls, config=config)


def test_dropbox_links_are_converted_to_direct_downloads() -> None:
    assert normalize_download_url("https://www.dropbox.com/s/example/Guide.pdf?dl=0") == (
        "https://www.dropbox.com/s/example/Guide.pdf?dl=1"
    )


def test_pdf_type_uses_original_url_and_pdf_magic_bytes() -> None:
    assert document_type_for("https://www.dropbox.com/s/example/Guide.pdf?dl=1", "application/octet-stream") == "pdf"
    assert document_type_for("https://example.com/download", "application/octet-stream", b"%PDF-1.7") == "pdf"


def test_extract_links_returns_url_and_anchor_text() -> None:
    links = extract_links(
        "https://chemistry.mit.edu/dcif/",
        b'<a href="/guide.pdf">Quick start guide - LCMS</a>',
    )

    assert links == [("https://chemistry.mit.edu/guide.pdf", "Quick start guide - LCMS")]
