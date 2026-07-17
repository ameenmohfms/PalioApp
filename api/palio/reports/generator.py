"""Clinician-ready summary generator (spec §9).

Contents are strictly: user-confirmed patterns, completed screener scores
with instrument name/version/date, strategies tried with outcomes, and —
only if the user explicitly typed them into the report flow — medications,
labeled "user-reported". No hypotheses, no agent speculation, nothing
unconfirmed (tested). Every page carries the A4 disclaimure header.

Rendered as HTML (full RTL support) → PDF via WeasyPrint. No LLM call:
the report is assembled from structured data, so it cannot hallucinate.
"""

import html
import uuid
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from palio.audit.events import record_audit
from palio.db.models import (
    Locale,
    Pattern,
    PatternStatus,
    Report,
    ScreenerInstrument,
    ScreenerResult,
    StrategyLog,
    StrategyStatus,
    User,
)

log = structlog.get_logger()

DISCLAIMER = {
    "en": (
        "Palio is an AI wellness companion — not a clinician and not a diagnostic "
        "instrument, and it is not for emergencies. This summary contains self-reported, "
        "user-confirmed information and validated screening scores. It supports, and never "
        "replaces, professional evaluation."
    ),
    "ar": (
        "باليو رفيق ذكاء اصطناعي للعافية — ليس طبيباً وليس أداة تشخيص، ولا يُستخدم "
        "للطوارئ. يحتوي هذا الملخص على معلومات ذكرها المستخدم وأكّدها بنفسه ونتائج "
        "مقاييس تحرّي معتمدة. وهو يدعم التقييم المهني ولا يحل محله أبداً."
    ),
}

TITLES = {
    "en": {
        "report": "Palio — Summary for your clinician",
        "generated": "Generated",
        "concerns": "Presenting concerns & context (user-confirmed, in the user's words)",
        "screeners": "Screening results",
        "impact": "Functional impact (user-confirmed observations)",
        "strategies": "Strategies tried and outcomes",
        "meds": "Medications (user-reported, as typed by the user)",
        "wins": "Strengths and wins (user-confirmed)",
        "none": "None recorded.",
        "score": "Score",
        "band": "Band",
        "date": "Date",
        "instrument": "Instrument (version)",
    },
    "ar": {
        "report": "باليو — ملخص لعرضه على الطبيب",
        "generated": "تاريخ الإنشاء",
        "concerns": "الشكاوى والسياق (أكّدها المستخدم، بكلماته)",
        "screeners": "نتائج مقاييس التحرّي",
        "impact": "الأثر الوظيفي (ملاحظات أكّدها المستخدم)",
        "strategies": "الاستراتيجيات المجرّبة ونتائجها",
        "meds": "الأدوية (كما كتبها المستخدم، غير مُتحقَّق منها)",
        "wins": "نقاط القوة والإنجازات (أكّدها المستخدم)",
        "none": "لا يوجد.",
        "score": "النتيجة",
        "band": "النطاق",
        "date": "التاريخ",
        "instrument": "المقياس (الإصدار)",
    },
}

FEEDBACK_LABEL = {
    "en": {"helped": "helped", "did_not_help": "did not help", "partial": "partly helped"},
    "ar": {"helped": "ساعدت", "did_not_help": "لم تساعد", "partial": "ساعدت جزئياً"},
}


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _confirmed(db: Session, user_id: uuid.UUID) -> list[Pattern]:
    return list(
        db.execute(
            select(Pattern)
            .where(Pattern.user_id == user_id, Pattern.status == PatternStatus.confirmed)
            .order_by(Pattern.created_at)
        ).scalars()
    )


def _screeners(db: Session, user_id: uuid.UUID):
    return db.execute(
        select(ScreenerResult, ScreenerInstrument)
        .join(ScreenerInstrument, ScreenerResult.instrument_id == ScreenerInstrument.id)
        .where(ScreenerResult.user_id == user_id, ScreenerResult.taken_at.isnot(None))
        .order_by(ScreenerResult.taken_at)
    ).all()


def _strategies(db: Session, user_id: uuid.UUID) -> list[StrategyLog]:
    return list(
        db.execute(
            select(StrategyLog)
            .where(
                StrategyLog.user_id == user_id,
                StrategyLog.status.in_(
                    [StrategyStatus.tried, StrategyStatus.adapted, StrategyStatus.dropped]
                ),
            )
            .order_by(StrategyLog.created_at)
        ).scalars()
    )


def build_html(
    db: Session,
    user: User,
    *,
    language: str,
    user_medications: str | None = None,
) -> str:
    lang = language if language in ("en", "ar") else "en"
    t = TITLES[lang]
    rtl = lang == "ar"
    now = datetime.now(UTC)

    patterns = _confirmed(db, user.id)
    concerns = [p for p in patterns if p.type.value in ("trigger",)]
    impact = [p for p in patterns if p.type.value in ("context", "strategy_outcome")]
    wins = [p for p in patterns if p.type.value in ("win", "strength")]

    def items(rows) -> str:
        if not rows:
            return f"<p class='none'>{t['none']}</p>"
        return "<ul>" + "".join(f"<li>{_esc(r.text)}</li>" for r in rows) + "</ul>"

    screener_rows = _screeners(db, user.id)
    if screener_rows:
        cells = "".join(
            f"<tr><td>{_esc(inst.definition.get('title', inst.key))} (v{_esc(inst.version)})</td>"
            f"<td>{_esc(', '.join(f'{k}: {v}' for k, v in res.scores.items()))}</td>"
            f"<td>{_esc(res.band)}</td>"
            f"<td>{res.taken_at.date().isoformat()}</td></tr>"
            for res, inst in screener_rows
        )
        screeners_html = (
            f"<table><tr><th>{t['instrument']}</th><th>{t['score']}</th>"
            f"<th>{t['band']}</th><th>{t['date']}</th></tr>{cells}</table>"
        )
    else:
        screeners_html = f"<p class='none'>{t['none']}</p>"

    from palio.coaching import library

    strategy_rows = _strategies(db, user.id)
    if strategy_rows:
        lines = []
        for row in strategy_rows:
            strategy = library.get(row.strategy_key)
            title = strategy[lang]["title"] if strategy else row.strategy_key
            feedback = FEEDBACK_LABEL[lang].get(row.feedback.value, "") if row.feedback else ""
            outcome = f" — {_esc(row.outcome)}" if row.outcome else ""
            lines.append(f"<li>{_esc(title)}: {feedback}{outcome}</li>")
        strategies_html = "<ul>" + "".join(lines) + "</ul>"
    else:
        strategies_html = f"<p class='none'>{t['none']}</p>"

    meds_html = ""
    if user_medications and user_medications.strip():
        meds_html = (
            f"<h2>{t['meds']}</h2><p class='user-reported'>{_esc(user_medications.strip())}</p>"
        )

    return f"""<html dir="{'rtl' if rtl else 'ltr'}" lang="{lang}">
<head><meta charset="utf-8"><style>
  @page {{ margin: 2cm; }}
  body {{ font-family: 'Noto Naskh Arabic', 'FreeSerif', serif; color: #1F2933;
         line-height: 1.6; font-size: 12pt; }}
  .disclaimer {{ background: #EEF3F1; border: 1px solid #C9D6D0; border-radius: 6px;
                 padding: 10px 14px; font-size: 10pt; }}
  h1 {{ font-size: 17pt; }} h2 {{ font-size: 13pt; margin-top: 18px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #C9D6D0; padding: 6px 8px; font-size: 10.5pt;
            text-align: {'right' if rtl else 'left'}; }}
  .none {{ color: #52606D; }}
  .user-reported {{ border: 1px dashed #C9D6D0; padding: 8px; }}
  .meta {{ color: #52606D; font-size: 10pt; }}
</style></head>
<body>
  <div class="disclaimer">{DISCLAIMER[lang]}</div>
  <h1>{t["report"]}</h1>
  <p class="meta">{t["generated"]}: {now.date().isoformat()} · {_esc(user.nickname)}</p>
  <h2>{t["concerns"]}</h2>{items(concerns)}
  <h2>{t["impact"]}</h2>{items(impact)}
  <h2>{t["wins"]}</h2>{items(wins)}
  <h2>{t["screeners"]}</h2>{screeners_html}
  <h2>{t["strategies"]}</h2>{strategies_html}
  {meds_html}
</body></html>"""


def reports_dir() -> Path:
    import os

    path = Path(os.environ.get("REPORTS_DIR", Path(__file__).resolve().parents[2] / "reports_out"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate(
    db: Session,
    user: User,
    *,
    language: str | None = None,
    user_medications: str | None = None,
) -> Report:
    lang = language or user.locale.value
    html_text = build_html(db, user, language=lang, user_medications=user_medications)

    from weasyprint import HTML  # imported here: heavy native deps

    report_id = uuid.uuid4()
    file_path = reports_dir() / f"palio_report_{report_id.hex}.pdf"
    HTML(string=html_text).write_pdf(str(file_path))

    report = Report(
        id=report_id,
        user_id=user.id,
        language=Locale(lang if lang in ("ar", "en") else "en"),
        meta={
            "file": file_path.name,
            "includes_user_medications": bool(user_medications and user_medications.strip()),
        },
    )
    db.add(report)
    db.flush()
    # Report export is a primary success metric (§3/§9).
    record_audit(actor="user", action="report_exported", subject_id=user.id)
    return report
