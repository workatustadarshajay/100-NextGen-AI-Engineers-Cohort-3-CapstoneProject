import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_TRACING_V2"] = "false"


class _FakeInteraction:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeInteractions:
    def __init__(self, output_text: str) -> None:
        self._output_text = output_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeInteraction(self._output_text)


class FakeGeminiClient:
    """Stands in for genai.Client so tests never reach the network."""

    def __init__(self, output_text: str) -> None:
        self.interactions = _FakeInteractions(output_text)

    @property
    def calls(self) -> list[dict]:
        return self.interactions.calls


@pytest.fixture
def fake_gemini_client():
    def _build(payload) -> FakeGeminiClient:
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        return FakeGeminiClient(payload)

    return _build


@pytest.fixture
def make_pdf(tmp_path):
    def _build(name: str, lines: list[str]) -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        path = tmp_path / name
        pdf = canvas.Canvas(str(path), pagesize=A4)
        text_object = pdf.beginText(60, 780)
        for line in lines:
            text_object.textLine(line)
        pdf.drawText(text_object)
        pdf.save()
        return path

    return _build
