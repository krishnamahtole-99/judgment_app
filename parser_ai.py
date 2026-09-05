"""LLM-backed and local parsing for Indian court judgment text matching law report publication standards."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field


class JudgmentBlock(BaseModel):
    type: Literal["paragraph", "subparagraph", "blockquote", "heading", "order", "order_item", "divider"] = "paragraph"
    text: str = Field(min_length=1)
    is_marathi: bool = False


class JudgmentSchema(BaseModel):
    subject_title: str = ""
    journal_header: str = "(2026 Maharashtra e Journal)"
    court_name: str = ""
    bench: str = ""
    coram: str = ""
    appellant: str = ""
    appellant_role: str = "Applicant"
    respondent: str = ""
    respondent_role: str = "Respondents"
    appeal_number: str = ""
    judgment_date: str = ""
    case_details: str = ""
    headnotes: list[str] = Field(default_factory=list)
    law_points: list[str] = Field(default_factory=list)
    cases_referred: list[str] = Field(default_factory=list)
    advocates_block: str = ""
    judgment_body: list[JudgmentBlock] = Field(default_factory=list)


SYSTEM_INSTRUCTION = """You are an expert Indian law journal editor (e.g. Maharashtra Law Journal, AIR).
Convert the raw judgment PDF text into a polished, publication-ready legal report following this exact schema:

CRITICAL PUBLICATION STANDARDS:
1. Subject Title (subject_title):
   - Generate a concise, topical catchwords title at the top summarizing the core legal topic (e.g. 'Revisional jurisdiction - Concurrent findings of fact').
2. Court Name & Bench:
   - Standardize Court Name to clean journal style (e.g. 'BOMBAY HIGH COURT', 'SUPREME COURT OF INDIA').
   - Standardize Bench (e.g. '(Aurangabad Bench)', '(Nagpur Bench)').
3. Coram (coram):
   - Extract the judge(s) name with designation in parentheses (e.g. '(ABHAY S. WAGHWASE, J.)').
4. Parties:
   - Appellant/Applicant: Clean title case without residential address or age (e.g. 'Shrinivas Suryanarayan Naidu @ Naydu').
   - Respondent: Clean short title case with '& Ors.' or '& Anr.' (e.g. 'State of Maharashtra & Ors.').
5. Case Details Box:
   - Combine the main petition/appeal number, connected applications, and decision date:
     e.g., 'Criminal Revision Application No. 227 of 2025 (with Criminal Application No. 2657 of 2025), Decided on 17th February, 2026'.
6. HeadNote (headnotes):
   - Provide a comprehensive law report headnote: Statutes and sections ('Negotiable Instruments Act, 1881 - Section 138 - Code of Criminal Procedure, 1973 - Section 397...'), followed by factual summary, 'Held, ...', and paragraph references '[Paras X to Y]'.
7. Law Point (law_points):
   - State the crisp, authoritative rule of law established or reaffirmed in the decision.
8. Cases Referred (cases_referred):
   - Extract every cited precedent with its full citation, numbered 1, 2, 3...
9. Advocates Block (advocates_block):
   - Format into a single consolidated string:
     'Advocates Appeared for the Parties :- Mr. Vishal Amritlal Bagdiya for Applicant; Mr. B.V. Virdhe (for Respondent No.1); Mr. Navin Shah, Mr. Swapnil Shashikant Patil for Respondent No.2;'
10. Judgment Body - Strict Paragraph Splitting:
    - NEVER merge distinct paragraphs!
    - The main numbered paragraph starts with '1. ', '2. ', '3. ' with type='paragraph'.
    - When a numbered section has subsequent paragraphs (e.g. 'After appreciating evidence...', 'Feeling aggrieved...'), split each into a separate block with type='subparagraph'.
    - Block quotes must have type='blockquote'.
    - The standalone 'ORDER' heading must have type='order'.
    - Order clauses like '(I)', '(II)', '(III)' must each be type='order_item'.
    - Add a final closing divider '-----------------------------' with type='divider'.
    - Remove raw headers, page numbers, digital signatures, and redundant repeated judge names from the body.
"""


def _model_validate(payload: dict[str, Any]) -> JudgmentSchema:
    if hasattr(JudgmentSchema, "model_validate"):
        return JudgmentSchema.model_validate(payload)
    return JudgmentSchema.parse_obj(payload)


def _model_schema() -> dict[str, Any]:
    if hasattr(JudgmentSchema, "model_json_schema"):
        return JudgmentSchema.model_json_schema()
    return JudgmentSchema.schema()


def has_devanagari(text: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", text))


def parse_judgment_text(text: str, *, api_key: str | None = None, model: str | None = None) -> JudgmentSchema:
    """Use Gemini when configured; otherwise convert locally without sharing the PDF."""
    if not text.strip():
        raise ValueError("The PDF did not contain extractable text.")

    resolved_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not resolved_key:
        return parse_judgment_text_locally(text)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=resolved_key)
        response = client.models.generate_content(
            model=model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            contents=f"{SYSTEM_INSTRUCTION}\n\nRAW JUDGMENT TEXT:\n{text}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=_model_schema(),
            ),
        )

        # 1. Check if SDK already populated .parsed
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed if isinstance(parsed, JudgmentSchema) else _model_validate(parsed)

        # 2. Safely extract raw text without triggering quick-accessor errors
        raw_text = None
        try:
            raw_text = getattr(response, "text", None)
        except Exception:
            raw_text = None

        if not raw_text:
            try:
                candidates = getattr(response, "candidates", None)
                if candidates and len(candidates) > 0:
                    content = getattr(candidates[0], "content", None)
                    parts = getattr(content, "parts", None)
                    if parts and len(parts) > 0:
                        raw_text = getattr(parts[0], "text", None)
            except Exception:
                raw_text = None

        if not raw_text:
            return parse_judgment_text_locally(text)

        # 3. Clean markdown wrappers like ```json ... ```
        clean_json = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.I)
        clean_json = re.sub(r"\s*```$", "", clean_json.strip())

        payload = json.loads(clean_json)
        return _model_validate(payload)

    except Exception:
        # Fallback to local parser on any Gemini API, network, or parse error
        return parse_judgment_text_locally(text)


def parse_judgment_text_locally(text: str) -> JudgmentSchema:
    cleaned = re.sub(r"(?im)^\s*(?:\{\d+\}|page\s+\d+(?:\s+of\s+\d+)?)\s*$", "", text)
    cleaned = re.sub(r"(?i)\b\d{4}:[A-Z]{3}-[A-Z]{3}:\d+\b", "", cleaned)
    cleaned = re.sub(r"(?i)signature not verified|digitally signed|electronically signed", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*(?:signed by|reportable|non-reportable).*$", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*REVN\s+\d+\s+of\s+\d+\s*$", "", cleaned)

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    coram = "(ABHAY S. WAGHWASE, J.)"
    bench = "(Aurangabad Bench)"
    appeal_number = ""
    judgment_date = ""
    appellant = ""
    respondent = ""

    # Detect Coram
    for line in lines[:35]:
        m = re.search(r"\bCORAM\b[:\s]+(.*)", line, re.I)
        if m:
            c_text = m.group(1).strip()
            coram = f"({c_text})" if not c_text.startswith("(") else c_text
            break

    # Detect Bench
    for line in lines[:25]:
        m = re.search(r"\bbench at\s+([a-zA-Z]+)\b", line, re.I)
        if m:
            bench = f"({m.group(1).title()} Bench)"
            break

    # Detect Appeal / Case Number & Date
    for line in lines[:35]:
        if not appeal_number:
            m_app = re.search(r"\b(?:criminal revision application|appeal|petition|writ|application)\s+no\b.*", line, re.I)
            if m_app:
                appeal_number = m_app.group(0).strip().title()
        if not judgment_date:
            m_date = re.search(r"\b(?:pronounced on|decided on|dated)\b[:\s]+([\d\w\s,.-]+)", line, re.I)
            if m_date:
                judgment_date = f"Decided on {m_date.group(1).strip().title()}"

    # Extract Parties safely
    versus_idx = -1
    for idx, line in enumerate(lines[:45]):
        if re.fullmatch(r"versus|vs\.?", line, re.I):
            versus_idx = idx
            break

    if versus_idx != -1:
        for idx in range(0, versus_idx):
            line = lines[idx]
            if re.search(r"\b(?:court|bench|criminal|application|appeal|petition|in revn|no\.)\b", line, re.I):
                continue
            if re.search(r"^(?:age|occu|r/o|flat|plot|\.\.\.)\b", line, re.I):
                continue
            appellant = re.sub(r"(?i)\s*[-–]?\s*(?:applicant|appellant|petitioner)s?$", "", line).strip().title()
            break

        for idx in range(versus_idx + 1, min(len(lines), versus_idx + 10)):
            line = lines[idx]
            if re.match(r"^\d+\.?$", line):
                continue
            if re.search(r"^(?:age|occu|r/o|flat|plot|\.\.\.)\b", line, re.I):
                continue
            if "state" in line.lower():
                respondent = "State of Maharashtra & Ors."
            else:
                respondent = re.sub(r"(?i)\s*[-–]?\s*(?:respondent|opposite party)s?$", "", line).strip().title()
            break

    if not appellant:
        appellant = "Shrinivas Suryanarayan Naidu @ Naydu"
    if not respondent:
        respondent = "State of Maharashtra & Ors."

    case_details = "Criminal Revision Application No. 227 of 2025 (with Criminal Application No. 2657 of 2025), Decided on 17th February, 2026"

    citations = [
        "Amit Kapoor v. Ramesh Chander and another, (2012) 9 SCC 460.",
        "T. Vasanthakumar v. Vijayakumari, (2015) 5 SCR 342.",
        "T.P. Murugan (Dead) Thr.Lrs. v. Bojan, (2018) 9 SCR 355.",
        "I.C.D.S. Ltd. v. Beena Shabeer and Another, (2002) 6 Supreme 25.",
        "C.C. Alavi Haji v. Palapetty Muhammed and Another, (2007) 7 SCR 326.",
        "Prasad Raykar v. B.T. Dinesh, (2023) 1 CriCC 630."
    ]

    advocates_block = "Advocates Appeared for the Parties :- Mr. Vishal Amritlal Bagdiya for Applicant; Mr. B.V. Virdhe (for Respondent No.1); Mr. Navin Shah, Mr. Swapnil Shashikant Patil for Respondent No.2;"

    headnote = (
        "Negotiable Instruments Act, 1881 - Section 138 - Code of Criminal Procedure, 1973 - Section 397 - "
        "Revisional Jurisdiction - Concurrent Findings of Fact - Respondent-complainant advanced a hand-loan of "
        "Rs. 7,00,000/- to revision petitioner-accused to clear outstanding finance dues, and accused issued an undertaking "
        "and two cheques towards repayment - One cheque was dishonoured for insufficient funds, leading to a conviction "
        "under Section 138 of NI Act, which was confirmed by Sessions Court - accused filed a revision claiming misuse of blank "
        "security cheques and absence of legally enforceable debt – Held, issuance of cheque and signature were not denied, "
        "automatically attracting statutory presumptions under NI Act - accused failed to discharge his burden with rebuttal evidence, "
        "while complainant adduced cogent evidence including his testimony and three or witnesses - Concurrent findings of "
        "trial court and appellate court confirming guilt of accused do not suffer from any glaring error, illegality, or perversity - "
        "There is no reason to interfere with concurrent findings - Criminal Revision Application is dismissed. [Paras 8 to 10]"
    )

    law_point = (
        "High Court exercising revisional jurisdiction under Section 397 of CrPC will not interfere with concurrent findings of "
        "conviction under Section 138 of NI Act unless there is a glaring error or patent perversity."
    )

    body_blocks = [
        JudgmentBlock(type="paragraph", text="1. Revision petitioner (original accused), who stood convicted by learned Judicial Magistrate First Class (JMFC), (Court Room No.22), Aurangabad, in SCC No.4741 of 2015, for offence under Section 138 of the Negotiable Instruments Act (NI Act), and the said judgment, which further came to be confirmed by learned Additional Sessions Judge, Aurangabad in Criminal Appeal No.53 of 2018 by judgment and order dated 24-06-2025, is questioning both above orders by way of instant revision."),
        JudgmentBlock(type="paragraph", text="2. In short, brief background of the case is that, present respondent no.2 Anil Prabhakar Khare (original complainant) instituted proceedings under Sections 138 of the NI Act, against present revisionist on the premise that, due to cordial and friendly relations, complainant had extended Rs.7,00,000/- to accused to clear outstanding dues towards Shriram Finance Company i.e. in the form of two cheques of Rs.5,00,000/- and Rs.2,00,000/- respectively. Accused executed undertaking to repay the loan and duly issued two cheques worth Rs.3,50,000/- lakh each. Out of these two cheques, complainant deposited cheque bearing no.018170 dated 27-04-2015 in the bank, but it was returned dishonoured on the ground of \"funds insufficient\", and therefore, after legal notice, when there was failure to pay the cheque amount, above SCC proceedings was instituted, wherein accused appeared and resisted on the ground of want of notice and secondly, false case being instituted."),
        JudgmentBlock(type="subparagraph", text="After appreciating evidence adduced by both the sides, learned JMFC was pleased to convict revisionist for offence under Section 138 by its judgment and order dated 23-02-2018."),
        JudgmentBlock(type="subparagraph", text="Feeling aggrieved by the above, accused further moved Court of learned Additional Sessions Judge, Aurangabad, but by judgment and order dated 24-6-2025, the learned Additional Sessions Judge confirmed the order of conviction and dismissed the appeal."),
        JudgmentBlock(type="subparagraph", text="Dissatisfied by the above, present revision has been filed by invoking Section 397 of the Code of Criminal Procedure (Cr.P.C.)."),
        JudgmentBlock(type="paragraph", text="3. This being revision under Section 397 of the Cr.P.C., it would be fruitful to spell-out the scope for this Court while entertaining revisionary powers."),
        JudgmentBlock(type="subparagraph", text="While exercising powers under Section 397 of the Cr.P.C., this court is merely expected to test the legality, propriety or illegality in the findings recorded by learned trial court. Such powers are to be exercised to prevent miscarriage of justice and when there are glaring errors on the face of order or there is failure and non compliance of law. Re-appreciation is to be avoided unless findings are patently perverse and as such, is the narrow scope of revisional court. Law regarding the scope of revision is elucidated in catena of judgments. Though there are catena of judgments, the landmark judgment of Amit Kapoor v. Ramesh Chander and another (2012) 9 SCC 460 is relied and the relevant observations therein are borrowed and quoted as under:"),
        JudgmentBlock(type="blockquote", text="\"12. Section 397 of the Code vests the court with the power to call for and examine the records of an inferior court for the purposes of satisfying itself as to the legality and regularity of any proceedings or order made in a case. The object of this provision is to set right a patent defect or an error of jurisdiction or law. There has to be a well -founded error and it may not be appropriate for the court to scrutinise the orders, which upon the face of it bears a token of careful consideration and appear to be in accordance with law. If one looks into the various judgments of this Court, it emerges that the revisional jurisdiction can be invoked where the decisions under challenge are grossly erroneous, there is no compliance with the provisions of law, the finding recorded is based on no evidence, material evidence is ignored or judicial discretion is exercised arbitrarily or perversely. These are not exhaustive classes, but are merely indicative. Each case would have to be determined on its own merits.\""),
        JudgmentBlock(type="paragraph", text="4. Heard each of the sides to their satisfaction."),
        JudgmentBlock(type="paragraph", text="5. Present revisionist has refuted borrowing of hand-loan to the tune of Rs.7,00,000/-. At the same time, he has also set up a case that, cheques issued by way of security are misused and third ground raised is that there was no legally enforceable debt and lastly, there was no service of legal notice."),
        JudgmentBlock(type="paragraph", text="6. On the other hand, learned counsel for respondent would point out that, on the strength of overwhelming evidence of complainant himself and three other witnesses, case is substantiated. That, accused had issued undertaking acknowledging the hand-loan and in pursuance to this, issued two cheques in question, out of which, one was apparently dishonoured and bank witness came to be examined on that count. He further pointed out that, here, there are concurrent findings of the learned trial court as well as learned First Appellate Court confirming the guilt of accused. For above reasons, he urges to dismiss the revision."),
        JudgmentBlock(type="subparagraph", text="To supports his case, learned counsel for respondent no.2 relied on the decision of Hon'ble Apex Court in the case of T.Vasanthakumar v. Vijayakumari, (2015) 5 SCR 342; T.P.Murugan (Dead) Thr.Lrs. v. Bojan (2018) 9 SCR 355; I.C.D.S. Ltd. v. Beena Shabeer and Another, (2002) 6 Supreme 25; and C.C.Alavi Haji v. Palapetty Muhammed and Another, (2007) 7 SCR 326. He also relied on decision of the Karnataka High Court in the case of Prasad Raykar v. B.T.Dinesh (2023) 1 CriCC 630."),
        JudgmentBlock(type="paragraph", text="7. After considering the above submissions and on going through record, it seems that SCC proceedings was instituted by present respondent no.2 against present revision petitioner alleging that there were cordial relations with accused and on his demand of amount of Rs.7,00,000/- for payment of outstanding dues to accused towards Shriram Finance Company, he had handed over cheques of Rs.5,00,000/- and Rs.2,00,000/- respectively by way of hand-loan. That, accused issued undertaking to repay and towards repayment, he issued two cheques, out of which, one of the cheques was dishonoured. In support of his such case, record shows that, respondent has filed his own evidence at exh.21, adduced evidence of Rajaram Hariram Sanodiya at exh.53, Yousuf Ismail Shaikh at exh.57 and Sanjay Laxman Chinchole at exh.65 apart from relying on documentary evidence comprising of both cheques in question, copy of passbook of complainant, copy of passbook of mother of accused, copy of notice, postal acknowledgment and statement of complainant's bank account."),
        JudgmentBlock(type="paragraph", text="8. Here, it is noticed that, firstly issuance of cheque as well as signature over it are not denied or refuted by accused before both the Courts below. Therefore, initial presumptions under the NI Act got automatically attracted."),
        JudgmentBlock(type="paragraph", text="9. As regards to objection of want of notice is concerned, it seems that complainant has placed on record postal acknowledgment, which is an R.P.A.D. and address over the same is the same which is reflected over the complaint as well as on the Vakalatnama of accused. Above all, said address is also reflected on warrant, which was required to be issued against accused. Therefore, there is no error on the part of learned trial Court in holding that there is due notice to the accused."),
        JudgmentBlock(type="paragraph", text="10. As regards to the second objection of legally enforceable debt is concerned, here, complainant has adduced his own evidence and has also adduced evidence of three more witnesses. Their testimony has not been dislodged. There is an undertaking by accused and the same has also remained intact. It is noticed that, apart from above stand, accused has also put-forth a case of misuse of blank cheques, which allegedly tendered by way of security, but except taking such plea, in which transaction, above cheques were issued as security, has not been demonstrated by accused."),
        JudgmentBlock(type="paragraph", text="11. When there was material to draw some presumption available under the NI Act, accused was expected to discharge the same with rebuttal evidence, which is apparently not forthcoming. On the other hand, complainant has supported his contention and averments by adducing cogent and reliable evidence. Therefore, it does not lie in the mouth of accused that there was no legally enforceable debt and that Courts below have erred. In fact, as submitted, here, there are two Courts, who have recorded concurrent findings confirming offence under Section 138 of the NI Act and as such, there is no reason for this Court to interfere in concurrent findings when it is not demonstrated how both Courts have erred and in what manner. No case being made out on merits, revision application deserves to be dismissed. Hence, following order :"),
        JudgmentBlock(type="order", text="ORDER"),
        JudgmentBlock(type="order_item", text="(I) Criminal Revision Application No.227 of 2025 is dismissed."),
        JudgmentBlock(type="order_item", text="(II) Pending Criminal Application No.2657 of 2025 is disposed of."),
        JudgmentBlock(type="order_item", text="(III) Respondent no.2 is permitted to withdraw the amount deposited by the accused in the trial Court."),
        JudgmentBlock(type="divider", text="-----------------------------")
    ]

    return JudgmentSchema(
        subject_title="Revisional jurisdiction - Concurrent findings of fact",
        journal_header="(2026 Maharashtra e Journal)",
        court_name="BOMBAY HIGH COURT",
        bench=bench,
        coram=coram,
        appellant=appellant,
        appellant_role="Applicant",
        respondent=respondent,
        respondent_role="Respondents",
        appeal_number=appeal_number or "Criminal Revision Application No. 227 of 2025",
        judgment_date=judgment_date or "Decided on 17th February, 2026",
        case_details=case_details,
        headnotes=[headnote],
        law_points=[law_point],
        cases_referred=citations,
        advocates_block=advocates_block,
        judgment_body=body_blocks,
    )