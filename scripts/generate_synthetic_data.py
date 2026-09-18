"""Generate a deterministic synthetic corpus of guideline and patient report PDFs."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

from app.config import get_ai_settings


SEED = 20260918

GUIDELINES: list[dict[str, object]] = [
    {
        "title": "Anaemia Investigation Pathway",
        "source": "Neuron Clinical Protocol Library",
        "sections": [
            ("Initial assessment", "Confirm a low haemoglobin result with a repeat full blood count before starting any investigation. Record symptom duration, fatigue severity, dizziness, and any reported bleeding. Review medicines that can contribute to anaemia."),
            ("Iron studies", "Request ferritin, serum iron, transferrin saturation, and B12 with folate when haemoglobin is below the reference range. A ferritin below 30 micrograms per litre indicates iron deficiency and requires a source of blood loss to be identified."),
            ("Escalation", "Haemoglobin below 80 grams per litre, or any haemoglobin fall with chest pain, breathlessness at rest, or syncope, requires same-day clinical assessment. Arrange urgent review rather than routine follow-up."),
            ("Follow-up", "Recheck the full blood count six to eight weeks after starting oral iron. Refer to gastroenterology when iron deficiency anaemia is confirmed in adults without an obvious cause."),
        ],
    },
    {
        "title": "Chronic Kidney Disease Monitoring Standard",
        "source": "Neuron Renal Care Standards",
        "sections": [
            ("Baseline testing", "Assess renal function with serum creatinine and estimated glomerular filtration rate. Confirm any abnormal result with a repeat sample within two weeks before assigning a chronic kidney disease stage."),
            ("Albuminuria", "Measure the urine albumin to creatinine ratio on an early morning sample. A ratio above 3 milligrams per millimole is significant and should be confirmed on a second sample."),
            ("Medication review", "Review ACE inhibitors, angiotensin receptor blockers, diuretics, and non-steroidal anti-inflammatory drugs when renal function declines. Check potassium and creatinine one to two weeks after a dose change."),
            ("Escalation", "An estimated glomerular filtration rate below 30 millilitres per minute, a sustained fall of more than 25 percent, or potassium above 6.0 millimoles per litre needs urgent nephrology discussion."),
        ],
    },
    {
        "title": "Lipid Management and Cardiovascular Risk",
        "source": "Neuron Cardiometabolic Guidelines",
        "sections": [
            ("Risk assessment", "Use a full lipid profile alongside blood pressure, smoking status, and family history to estimate ten-year cardiovascular risk before offering treatment."),
            ("Targets", "Aim for a greater than 40 percent reduction in non-HDL cholesterol after starting a statin. Recheck the lipid profile three months after initiation or a dose change."),
            ("Lifestyle", "Offer structured dietary advice, weight management, and physical activity support alongside any pharmacological therapy."),
            ("Escalation", "Total cholesterol above 9 millimoles per litre or triglycerides above 20 millimoles per litre suggests a familial or secondary cause and requires specialist lipid clinic referral."),
        ],
    },
    {
        "title": "Thyroid Function Interpretation Guide",
        "source": "Neuron Endocrine Protocol Library",
        "sections": [
            ("Interpretation", "Interpret thyroid stimulating hormone together with free thyroxine. An isolated abnormal thyroid stimulating hormone result should be repeated after two to three months before treatment."),
            ("Hypothyroidism", "Start levothyroxine when thyroid stimulating hormone is persistently raised with a low free thyroxine. Recheck thyroid function six to eight weeks after any dose change."),
            ("Hyperthyroidism", "A suppressed thyroid stimulating hormone with a raised free thyroxine warrants endocrine referral. Check for atrial fibrillation in older patients."),
            ("Escalation", "Thyroid stimulating hormone above 10 milliunits per litre with symptoms, or any suspicion of thyroid storm, requires urgent specialist input."),
        ],
    },
    {
        "title": "Glycaemic Control and Diabetes Review",
        "source": "Neuron Cardiometabolic Guidelines",
        "sections": [
            ("Diagnosis", "Confirm diabetes with a glycated haemoglobin of 48 millimoles per mole or above on two occasions in an asymptomatic patient."),
            ("Monitoring", "Repeat glycated haemoglobin every three to six months until stable, then every six months. Review adherence and lifestyle before intensifying therapy."),
            ("Complication screening", "Arrange annual retinal screening, foot assessment, and urine albumin to creatinine ratio for every patient with diabetes."),
            ("Escalation", "Glycated haemoglobin above 86 millimoles per mole, or any episode of severe hypoglycaemia, requires prompt specialist diabetes review."),
        ],
    },
    {
        "title": "Liver Function Abnormality Workup",
        "source": "Neuron Hepatology Standards",
        "sections": [
            ("First steps", "Repeat abnormal liver enzymes after four weeks unless the patient is unwell. Record alcohol intake, medicines, and metabolic risk factors."),
            ("Non-invasive testing", "Request a liver screen including viral serology and an ultrasound when transaminases remain raised beyond three months."),
            ("Escalation", "Alanine aminotransferase above five times the upper limit of normal, or any jaundice with coagulopathy, requires same-day hepatology assessment."),
            ("Follow-up", "Recheck liver function three months after a medication change that could account for the abnormality."),
        ],
    },
    {
        "title": "Vitamin D and Bone Health Protocol",
        "source": "Neuron Clinical Protocol Library",
        "sections": [
            ("Testing", "Measure serum 25-hydroxyvitamin D only when deficiency is clinically suspected or in patients with malabsorption or bone disease."),
            ("Replacement", "Treat levels below 25 nanomoles per litre with loading doses followed by maintenance therapy, and recheck after three to six months."),
            ("Calcium", "Check adjusted calcium before starting high-dose vitamin D to exclude undiagnosed hypercalcaemia."),
            ("Escalation", "Adjusted calcium above 3.0 millimoles per litre is a medical emergency and requires immediate assessment."),
        ],
    },
    {
        "title": "Inflammatory Marker Assessment",
        "source": "Neuron Diagnostics Library",
        "sections": [
            ("Context", "Interpret C-reactive protein and erythrocyte sedimentation rate alongside the clinical picture. Neither marker is diagnostic on its own."),
            ("Persistent elevation", "Investigate a persistently raised C-reactive protein with a full blood count, renal and liver profile, and imaging guided by symptoms."),
            ("Escalation", "A C-reactive protein above 100 milligrams per litre with fever or haemodynamic instability suggests serious infection and needs immediate review."),
            ("Documentation", "Record the suspected source and the planned reassessment interval whenever an inflammatory marker is abnormal."),
        ],
    },
    {
        "title": "Electrolyte Disturbance Management",
        "source": "Neuron Acute Care Standards",
        "sections": [
            ("Sodium", "Confirm hyponatraemia with paired serum and urine osmolality. Correct chronic hyponatraemia slowly to avoid osmotic demyelination."),
            ("Potassium", "Repeat any potassium result above 6.0 millimoles per litre immediately and obtain an electrocardiogram. Haemolysis is a common cause of spurious results."),
            ("Review", "Review diuretics, ACE inhibitors, and potassium supplements whenever an electrolyte disturbance is found."),
            ("Escalation", "Potassium above 6.5 millimoles per litre, or sodium below 120 millimoles per litre, requires emergency management."),
        ],
    },
    {
        "title": "Medication Reconciliation Standard",
        "source": "Neuron Medication Safety Library",
        "sections": [
            ("Process", "Reconcile the full medication list at every clinical encounter, including over-the-counter and herbal products."),
            ("High-risk drugs", "Pay particular attention to anticoagulants, insulin, methotrexate, lithium, and diuretics because these carry the highest harm potential."),
            ("Monitoring", "Confirm that the required monitoring bloods for each high-risk medicine are up to date and document the next due date."),
            ("Escalation", "Any suspected adverse drug reaction that caused harm should be reported and reviewed by the prescribing clinician within one working day."),
        ],
    },
]

PANELS: dict[str, list[tuple[str, str, str, tuple[float, float]]]] = {
    "Full blood count": [
        ("Haemoglobin", "g/L", "130 - 175", (70.0, 180.0)),
        ("White cell count", "x10^9/L", "4.0 - 11.0", (3.0, 16.0)),
        ("Platelets", "x10^9/L", "150 - 400", (90.0, 460.0)),
        ("Mean cell volume", "fL", "80 - 100", (70.0, 105.0)),
    ],
    "Renal profile": [
        ("Creatinine", "umol/L", "60 - 110", (55.0, 260.0)),
        ("eGFR", "mL/min", "> 90", (20.0, 120.0)),
        ("Potassium", "mmol/L", "3.5 - 5.3", (3.0, 6.8)),
        ("Sodium", "mmol/L", "133 - 146", (118.0, 150.0)),
    ],
    "Liver profile": [
        ("Alanine aminotransferase", "U/L", "10 - 45", (8.0, 240.0)),
        ("Bilirubin", "umol/L", "3 - 20", (2.0, 60.0)),
        ("Albumin", "g/L", "35 - 50", (28.0, 52.0)),
    ],
    "Metabolic profile": [
        ("Glycated haemoglobin", "mmol/mol", "20 - 41", (28.0, 96.0)),
        ("Total cholesterol", "mmol/L", "< 5.0", (3.2, 9.6)),
        ("Thyroid stimulating hormone", "mU/L", "0.4 - 4.0", (0.1, 12.0)),
        ("C-reactive protein", "mg/L", "< 5", (1.0, 130.0)),
    ],
}

FIRST_NAMES = ["Jordan", "Amara", "Priya", "Marcus", "Elena", "Tobias", "Neha", "Rowan", "Sofia", "Idris"]
LAST_NAMES = ["Ellis", "Okafor", "Raman", "Delgado", "Novak", "Fischer", "Sharma", "Bennett", "Moreau", "Haddad"]
CONCERNS = [
    "Persistent fatigue and intermittent dizziness",
    "Routine chronic disease monitoring",
    "Breathlessness on exertion for three weeks",
    "Unintentional weight loss over two months",
    "Follow-up after abnormal screening bloods",
]
HISTORIES = [
    "Symptoms reported over the last six weeks with no acute distress noted.",
    "Known hypertension managed in primary care for four years.",
    "Type 2 diabetes diagnosed in 2019, reviewed annually.",
    "No significant past medical history recorded.",
    "Previous iron deficiency treated with a three-month oral course.",
]
MEDICATIONS = [
    "Lisinopril 10 mg daily; vitamin D supplement",
    "Metformin 1 g twice daily",
    "Atorvastatin 20 mg nightly; aspirin 75 mg daily",
    "Levothyroxine 75 micrograms daily",
    "No regular medication",
]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("NeuronTitle", parent=base["Title"], fontSize=16, spaceAfter=10),
        "heading": ParagraphStyle("NeuronHeading", parent=base["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("NeuronBody", parent=base["BodyText"], fontSize=10, leading=14),
    }


def _write_guideline(guideline: dict[str, object], output_dir: Path) -> Path:
    styles = _styles()
    slug = str(guideline["title"]).lower().replace(" ", "-")
    path = output_dir / f"{slug}.pdf"
    document = SimpleDocTemplate(
        str(path), pagesize=A4, title=str(guideline["title"]),
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    story = [
        Paragraph(str(guideline["title"]), styles["title"]),
        Paragraph(f"Source: {guideline['source']}", styles["body"]),
        Spacer(1, 8),
    ]
    for heading, text in guideline["sections"]:  # type: ignore[union-attr]
        story.append(Paragraph(heading, styles["heading"]))
        story.append(Paragraph(text, styles["body"]))
    document.build(story)
    return path


def _write_report(index: int, rng: random.Random, output_dir: Path) -> Path:
    styles = _styles()
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    patient_id = f"PX-{1000 + index}"
    panel_name = rng.choice(list(PANELS))
    rows = [["Test", "Result", "Unit", "Reference range"]]
    for test_name, unit, reference, (low, high) in PANELS[panel_name]:
        value = round(rng.uniform(low, high), 1)
        rows.append([test_name, str(value), unit, reference])

    path = output_dir / f"report-{patient_id.lower()}.pdf"
    document = SimpleDocTemplate(
        str(path), pagesize=A4, title=f"Clinical report {patient_id}",
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    table = Table(rows, colWidths=[62 * mm, 28 * mm, 28 * mm, 42 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f1f2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0b1c35")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d4dd")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story = [
        Paragraph("Neuron Clinical Laboratory Report", styles["title"]),
        Paragraph(f"Patient name: {first} {last}", styles["body"]),
        Paragraph(f"Patient ID: {patient_id}", styles["body"]),
        Paragraph(f"Date of birth: {rng.randint(1945, 2004)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", styles["body"]),
        Paragraph(f"Sex: {rng.choice(['Female', 'Male'])}", styles["body"]),
        Paragraph(f"Encounter date: 2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}", styles["body"]),
        Spacer(1, 10),
        Paragraph("Presenting concern", styles["heading"]),
        Paragraph(rng.choice(CONCERNS), styles["body"]),
        Paragraph("History", styles["heading"]),
        Paragraph(rng.choice(HISTORIES), styles["body"]),
        Paragraph("Current medication", styles["heading"]),
        Paragraph(rng.choice(MEDICATIONS), styles["body"]),
        Paragraph(f"{panel_name} results", styles["heading"]),
        table,
        Spacer(1, 10),
        Paragraph(
            "This is synthetic data generated for development and testing. It does not describe a real patient.",
            styles["body"],
        ),
    ]
    document.build(story)
    return path


def generate_corpus(report_count: int = 25) -> tuple[list[Path], list[Path]]:
    settings = get_ai_settings()
    guidelines_dir = settings.guidelines_dir
    reports_dir = settings.synthetic_dir / "reports"
    guidelines_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    guideline_paths = [_write_guideline(guideline, guidelines_dir) for guideline in GUIDELINES]
    rng = random.Random(SEED)
    report_paths = [_write_report(index, rng, reports_dir) for index in range(1, report_count + 1)]
    return guideline_paths, report_paths


if __name__ == "__main__":
    guidelines, reports = generate_corpus()
    print(f"Wrote {len(guidelines)} guideline PDFs and {len(reports)} synthetic report PDFs.")
