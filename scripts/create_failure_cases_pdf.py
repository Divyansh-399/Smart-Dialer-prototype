from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "smartdialer_failure_case_answers.pdf"


def body(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def section(number: str, title: str, question: str, answer: str, styles: dict) -> list:
    return [KeepTogether([
        Paragraph(f"{number}. {title}", styles["heading"]),
        body(f"<b>Question:</b> {question}", styles["body"]),
        body(f"<b>Answer:</b> {answer}", styles["body"]),
        Spacer(1, 4 * mm),
    ])]


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=16 * mm, bottomMargin=16 * mm)
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=21,
                                leading=26, textColor=colors.HexColor("#17324D"), spaceAfter=5 * mm),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=10.5, leading=15,
                                   textColor=colors.HexColor("#506B80"), spaceAfter=7 * mm),
        "heading": ParagraphStyle("Heading", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13,
                                  leading=16, textColor=colors.HexColor("#17324D"), spaceBefore=2 * mm, spaceAfter=2 * mm),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=9.6, leading=13.5, alignment=TA_LEFT,
                               spaceAfter=2 * mm),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontSize=8.5, leading=11.5,
                                textColor=colors.HexColor("#506B80")),
    }
    story = [Paragraph("SmartDialer - Failure Case Answers", styles["title"]),
             Paragraph("Implementation-specific answers for the Hiring 2026 technical assignment.", styles["subtitle"])]
    story += section("1", "Worker crash", "Agent reserved -> borrower reserved -> call initiated -> worker crashes. What happens when the system comes back?",
                     "The reservation is durable in the repository. On restart, <font name='Courier'>recover()</font> first queries the provider status for every non-terminal call and processes any returned events idempotently. If the provider confirms completion or failure, the call reaches that terminal state and its agent and borrower reservations are released. If status remains unknown, the call is cancelled and released rather than redialed. This prevents duplicate calls and prevents a stale reservation from blocking capacity forever.", styles)
    story += section("2", "Provider outage", "The provider starts timing out. What happens to existing calls, new calls, retries, and pacing?",
                     "Existing calls are reconciled from provider status; they are not blindly redialed. Definite pre-connect failures retry once through a different healthy provider. An unknown timeout is treated as unknown until status is checked using the call identity. The circuit breaker marks repeated failures unhealthy. When no provider is healthy, Safety Controller rejects new call requests and pacing effectively becomes zero. When a provider recovers, normal conservative pacing resumes.", styles)
    story += section("3", "Agent availability suddenly drops", "100 agents are available and 40 disappear within a few seconds. How quickly does the dialer react?",
                     "The agent-presence update calls <font name='Courier'>mark_agents_unavailable()</font> immediately. Those 40 agents stop counting as available before the next pacing decision. Any pre-connect call reserved to a disappeared agent is cancelled and its borrower reservation is released; already connected calls are not reassigned blindly. The next scheduling turn therefore approves capacity from the remaining protected agents only.", styles)
    story += section("4", "Duplicate events", "The same provider event arrives multiple times. Does the system create multiple state transitions?",
                     "No. Every provider event has a stable event ID stored on the call record. The first delivery is processed; later deliveries with the same ID are ignored. A terminal call also ignores all subsequent events. The result is one logical transition and one release of the agent and borrower reservation.", styles)
    story += section("5", "Out-of-order events", "Events do not arrive in the expected order. Does the system break?",
                     "No. The event processor accepts safe terminal events from an in-flight state and rejects invalid backward transitions. For example, a COMPLETED event can safely end an initiated or ringing call; a later ANSWERED event is ignored because the call is terminal. The chaotic mock provider and automated tests exercise duplicate and out-of-order delivery.", styles)
    data = [[body("Safety principle", styles["small"]), body("Never use an estimated answer rate as permission to abandon a caller.", styles["small"])]]
    table = Table(data, colWidths=[42 * mm, 128 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E9F3F8")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9FC2D3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C6DDE8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [Spacer(1, 2 * mm), table]
    document.build(story)


if __name__ == "__main__":
    build()
