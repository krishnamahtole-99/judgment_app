import os
from io import BytesIO

import pdfplumber
import streamlit as st

from parser_ai import parse_judgment_text
from docx_generator import generate_docx

st.set_page_config(page_title="Indian Judgment to Word", page_icon="⚖", layout="centered")
st.title("Indian Judgment to Word")
st.caption("Converts court judgment PDFs into legally formatted Microsoft Word (.docx) files according to exact legal styling rules.")

GEMINI_MODELS = {
    "Gemini 3.6 Flash": "gemini-3.6-flash",
    "Gemini 3.5 Flash": "gemini-3.5-flash",
    "Gemini 3.5 Pro": "gemini-3.5-pro",
}

with st.sidebar:
    st.header("Settings")
    google_api_key = st.text_input(
        "Google Gemini API key",
        value=os.getenv("GOOGLE_API_KEY", ""),
        type="password",
        help="Optional. Leave empty for local conversion on your device.",
    )
    configured_model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    model_names = list(GEMINI_MODELS)
    selected_model_name = st.selectbox(
        "Gemini model",
        model_names,
        index=(list(GEMINI_MODELS.values()).index(configured_model)
               if configured_model in GEMINI_MODELS.values() else 0),
        help="Choose which Gemini model parses the judgment when an API key is provided.",
    )
    selected_model = GEMINI_MODELS[selected_model_name]
    font_size = st.number_input("Word body font size", min_value=9, max_value=16, value=12, step=1)

uploaded_file = st.file_uploader("Upload a judgment PDF", type=["pdf"])

if uploaded_file is not None:
    try:
        pdf_stream = BytesIO(uploaded_file.getvalue())
        with pdfplumber.open(pdf_stream) as pdf:
            extracted_text = "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    except Exception as exc:
        st.error(f"Could not read this PDF: {exc}")
        st.stop()

    if not extracted_text:
        st.error("No selectable text was found. Please upload a searchable PDF or run OCR before uploading.")
        st.stop()

    with st.expander("Extracted text preview"):
        st.text(extracted_text[:3000])

    if st.button("Convert to Word (.docx)", type="primary"):
        progress_bar = st.progress(0, text="Starting conversion...")
        with st.spinner("Applying legal rules, styles, margins, and paragraph formatting..."):
            try:
                progress_bar.progress(30, text="Parsing parties, citations, and numbered points...")
                judgment = parse_judgment_text(
                    extracted_text,
                    api_key=google_api_key,
                    model=selected_model,
                )
                
                progress_bar.progress(70, text="Generating customized .docx with legal layout...")
                docx_stream = generate_docx(judgment, font_size=int(font_size))
                
                progress_bar.progress(100, text="Ready!")
            except Exception as exc:
                progress_bar.empty()
                st.error(f"Error during conversion: {exc}")
            else:
                st.success("Document successfully formatted!")
                st.subheader("Detected Case Metadata")
                col1, col2 = st.columns(2)
                with col1:
                    topic = getattr(judgment, 'subject_title', '') or 'Not detected'
                    applicant = getattr(judgment, 'appellant', '') or 'Not detected'
                    respondent = getattr(judgment, 'respondent', '') or 'Not detected'
                    bench = getattr(judgment, 'bench', '') or 'Not detected'
                    st.write(f"• **Topic:** {topic}")
                    st.write(f"• **Applicant:** {applicant}")
                    st.write(f"• **Respondent:** {respondent}")
                    st.write(f"• **Bench:** {bench}")
                with col2:
                    case_details = getattr(judgment, 'case_details', '') or 'Not detected'
                    cases_ref = getattr(judgment, 'cases_referred', []) or []
                    st.write(f"• **Case Details:** {case_details}")
                    st.write(f"• **Cases Referred:** {len(cases_ref)} cited")

                filename = f"{uploaded_file.name.rsplit('.', 1)[0]}_formatted.docx"
                st.download_button(
                    label="⬇ Download Formatted Word Document",
                    data=docx_stream.getvalue(),
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )