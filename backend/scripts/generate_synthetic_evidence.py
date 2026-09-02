"""Generate only fictional, labeled synthetic cybercrime evidence for safe DRISHYAM MVP validation."""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "generated_evidence"


def _font(size: int):
    for candidate in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def receipt_image() -> Path:
    target = OUTPUT / "upi_receipt_synthetic.png"
    image = Image.new("RGB", (1800, 1400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 70, 1720, 1330), outline="#7b1e2b", width=12)
    lines = [
        "SYNTHETIC TRAINING EVIDENCE — NOT A REAL RECEIPT",
        "UPI PAYMENT SUCCESSFUL",
        "Date: 14/08/2026 10:41",
        "Amount: INR 75,000.00",
        "Sender: AARAV SHARMA",
        "Receiver: Fraud Collect",
        "UPI ID: fraudcollect@upi",
        "UTR: SYNUPI202608141041",
        "Reference: DRISHYAM-DEMO-001",
    ]
    y = 140
    for index, line in enumerate(lines):
        draw.text((140, y), line, fill="#7b1e2b" if index < 2 else "#1f2933", font=_font(42 if index else 34))
        y += 125
    image.save(target)
    return target


def complaint_pdf() -> Path:
    target = OUTPUT / "complaint_statement_synthetic.pdf"
    pdf = canvas.Canvas(str(target), pagesize=A4)
    _, height = A4
    lines = [
        "SYNTHETIC TRAINING EVIDENCE — FICTIONAL COMPLAINT STATEMENT",
        "Complaint date: 14/08/2026 11:30",
        "Complainant alias: Aarav Sharma",
        "A job offer message was received from +91 9876543210.",
        "The sender used email jobs@skill-placement.example and URL https://skill-placement.example/verify.",
        "The sender requested an activation fee to fraudcollect@upi.",
        "A transfer of INR 75,000 was documented with UTR SYNUPI202608141041.",
        "A second transfer was sent to fraudcollect@upi from account 123456789012.",
        "IFSC stated in the message: TEST0001234.",
        "This fictional material is solely for backend validation.",
    ]
    text = pdf.beginText(48, height - 56)
    text.setFont("Helvetica", 12)
    for line in lines:
        text.textLine(line)
        text.textLine("")
    pdf.drawText(text)
    pdf.save()
    return target


def write_text_artifacts() -> list[Path]:
    whatsapp = OUTPUT / "whatsapp_chat_synthetic.txt"
    whatsapp.write_text(
        "SYNTHETIC TRAINING EVIDENCE — FICTIONAL CHAT\n"
        "14/08/2026, 09:05 AM - +91 9876543210: Hi Aarav Sharma, confirm your job offer at https://skill-placement.example/verify\n"
        "14/08/2026, 09:08 AM - +91 9876543210: Send INR 2500 registration fee to fraudcollect@upi. UTR SYNCHAT202608140908\n"
        "14/08/2026, 09:22 AM - +91 9123456789: Bank account 123456789012 IFSC TEST0001234 is also active.\n"
        "14/08/2026, 10:10 AM - +91 9876543210: Contact jobs@skill-placement.example. Transfer INR 75000 to fraudcollect@upi today.\n"
        "14/08/2026, 10:35 AM - +91 9988776655: Sender: Aarav Sharma. Receiver: Fraud Collect. Use reference SYNUPI202608141041.\n",
        encoding="utf-8",
    )
    phishing = OUTPUT / "phishing_offer_synthetic.eml"
    phishing.write_text(
        "From: Skill Placement <jobs@skill-placement.example>\n"
        "To: aarav.sharma@victim.invalid\n"
        "Subject: Synthetic offer verification required\n"
        "Date: Fri, 14 Aug 2026 09:01:00 +0000\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "This is fictional training content. Verify at https://skill-placement.example/verify?ref=DRI-2026. "
        "Contact +91 9876543210 and pay INR 2500 to fraudcollect@upi. Sender name: Mohit Verma.\n",
        encoding="utf-8",
    )
    bank = OUTPUT / "bank_statement_synthetic.csv"
    with bank.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "amount", "sender", "receiver", "reference", "note"])
        writer.writeheader()
        writer.writerows([
            {"date": "2026-08-14 10:41", "amount": "75000.00", "sender": "Aarav Sharma", "receiver": "fraudcollect@upi", "reference": "SYNUPI202608141041", "note": "Synthetic UPI transfer"},
            {"date": "2026-08-14 11:18", "amount": "52000.00", "sender": "Aarav Sharma", "receiver": "fraudcollect@upi", "reference": "SYNBANK202608141118", "note": "Synthetic second transfer"},
            {"date": "2026-08-14 12:55", "amount": "12000.00", "sender": "Aarav Sharma", "receiver": "mohit.verma@upi", "reference": "SYNBANK202608141255", "note": "Synthetic forwarding transfer"},
        ])
    calls = OUTPUT / "call_log_synthetic.csv"
    with calls.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "time", "direction", "number", "contact", "duration_seconds"])
        writer.writeheader()
        writer.writerows([
            {"date": "14/08/2026", "time": "09:00", "direction": "incoming", "number": "+919876543210", "contact": "Mohit Verma", "duration_seconds": "182"},
            {"date": "14/08/2026", "time": "09:31", "direction": "incoming", "number": "+919876543210", "contact": "Mohit Verma", "duration_seconds": "94"},
            {"date": "14/08/2026", "time": "10:34", "direction": "outgoing", "number": "+919988776655", "contact": "Fraud Collect", "duration_seconds": "70"},
            {"date": "14/08/2026", "time": "11:20", "direction": "incoming", "number": "+919123456789", "contact": "Bank Callback", "duration_seconds": "45"},
        ])
    return [whatsapp, phishing, bank, calls]


def generate() -> list[Path]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = write_text_artifacts()
    files.extend([receipt_image(), complaint_pdf()])
    return sorted(files)


if __name__ == "__main__":
    for artifact in generate():
        print(artifact)

