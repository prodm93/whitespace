"""Tests for the tri-modal normaliser."""

from __future__ import annotations

from whitespace.tools.normaliser import Normaliser

SAMPLE_USPTO = {
    "patent_number": "US11234567B2",
    "title": "Battery Cell with Improved Thermal Management",
    "abstract": "A battery cell comprising a thermal interface layer...",
    "claims": "1. A battery cell comprising: a cathode; an anode...",
    "description": "The present invention relates to battery technology.",
    "inventors": ["Alice Smith", "Bob Jones"],
    "cpc_codes": ["H01M10/6556", "H01M10/613"],
    "citations": ["US9876543B1"],
}


class TestFromUspto:
    def test_source_type_is_api(self) -> None:
        doc = Normaliser().from_uspto(SAMPLE_USPTO)
        assert doc.source_type == "api"

    def test_patent_number_as_source_name(self) -> None:
        doc = Normaliser().from_uspto(SAMPLE_USPTO)
        assert doc.source_name == "US11234567B2"

    def test_source_url_points_to_google_patents(self) -> None:
        doc = Normaliser().from_uspto(SAMPLE_USPTO)
        assert doc.source_url is not None
        assert "US11234567B2" in doc.source_url

    def test_content_includes_abstract_claims_description(self) -> None:
        doc = Normaliser().from_uspto(SAMPLE_USPTO)
        assert "thermal interface layer" in doc.content
        assert "cathode" in doc.content
        assert "battery technology" in doc.content

    def test_metadata_carries_inventors_and_cpc(self) -> None:
        doc = Normaliser().from_uspto(SAMPLE_USPTO)
        assert doc.metadata["inventors"] == ["Alice Smith", "Bob Jones"]
        assert doc.metadata["cpc_codes"] == ["H01M10/6556", "H01M10/613"]
        assert doc.metadata["citations"] == ["US9876543B1"]

    def test_empty_patent_number_falls_back_to_title(self) -> None:
        raw = {**SAMPLE_USPTO, "patent_number": ""}
        doc = Normaliser().from_uspto(raw)
        assert doc.source_name == SAMPLE_USPTO["title"]
        assert doc.source_url is None

    def test_minimal_fields(self) -> None:
        raw = {"patent_number": "US999", "title": "Minimal"}
        doc = Normaliser().from_uspto(raw)
        assert doc.source_type == "api"
        assert doc.title == "Minimal"
        assert doc.content == "Minimal"
        assert doc.metadata == {}


class TestFromWeb:
    def test_source_type_is_web(self) -> None:
        doc = Normaliser().from_web("https://example.com/article", "Some content")
        assert doc.source_type == "web"

    def test_source_url_preserved(self) -> None:
        url = "https://example.com/article"
        doc = Normaliser().from_web(url, "Some content")
        assert doc.source_url == url

    def test_source_name_is_url(self) -> None:
        url = "https://example.com/article"
        doc = Normaliser().from_web(url, "Some content")
        assert doc.source_name == url

    def test_title_from_first_line(self) -> None:
        content = "Battery Innovations in 2025\nLots of detail here..."
        doc = Normaliser().from_web("https://example.com", content)
        assert doc.title == "Battery Innovations in 2025"

    def test_title_falls_back_to_url_if_first_line_too_long(self) -> None:
        content = "x" * 300 + "\nShort second line"
        url = "https://example.com"
        doc = Normaliser().from_web(url, content)
        assert doc.title == url


class TestFromUpload:
    def test_source_type_is_pdf(self) -> None:
        doc = Normaliser().from_upload("patent_doc.pdf", "Full text here")
        assert doc.source_type == "pdf"

    def test_source_url_is_none(self) -> None:
        doc = Normaliser().from_upload("patent_doc.pdf", "Full text here")
        assert doc.source_url is None

    def test_source_name_is_filename(self) -> None:
        doc = Normaliser().from_upload("patent_doc.pdf", "Full text here")
        assert doc.source_name == "patent_doc.pdf"

    def test_content_preserved(self) -> None:
        content = "This is the full document content."
        doc = Normaliser().from_upload("doc.pdf", content)
        assert doc.content == content

    def test_title_from_first_line(self) -> None:
        content = "My Research Paper\nAbstract: blah blah"
        doc = Normaliser().from_upload("paper.pdf", content)
        assert doc.title == "My Research Paper"
