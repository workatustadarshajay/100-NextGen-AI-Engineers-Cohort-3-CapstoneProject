from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.models import DocumentStatus


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

STATUS_LABELS = {
    DocumentStatus.SUMMARISING.value: "Summarising",
    DocumentStatus.WORKFLOW_COMPLETED.value: "Workflow completed",
    DocumentStatus.HITL_COMPLETED.value: "HITL completed",
    DocumentStatus.FAILED.value: "Needs attention",
}


def status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value.replace("_", " ").title())


def format_datetime(value) -> str:
    return value.strftime("%d %b %Y, %H:%M") if value else "-"


def username_initials(user) -> str:
    username = (getattr(user, "email", "") or "").split("@", 1)[0].strip()
    return (username[:2] or "NR").upper()


def create_templates() -> Jinja2Templates:
    """Build a Jinja environment with every shared filter registered."""
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env.filters["status_label"] = status_label
    templates.env.filters["format_datetime"] = format_datetime
    templates.env.filters["username_initials"] = username_initials
    return templates
