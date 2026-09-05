# Indian Judgment to Word (.docx) Converter

A specialized legal document parsing and styling tool that converts Indian court judgment PDFs into accurately formatted Microsoft Word files according to strict legal and journal guidelines.

## Specifications Implemented

- **Page Layout:** Narrow Margins (0.5 inch / 36 pt on all 4 sides).
- **Default Spacing:** 5 pt space after paragraphs.
- **Parties Formatting:** Title Case with appended roles (`- Applicant` and `- Respondents`).
- **Case Details:** Bordered box containing Appeal Number, Date, and Case details.
- **Citations (Cases Referred):** Formatted with 0.4 cm left indent in 11.5 pt font with 2 pt spacing before.
- **Advocates:** Formatted with 0.21 cm left indent, 5 pt spacing before, 4.1 pt spacing after.
- **Judgment Body:**
  - **Decimal numbered paragraphs (1., 2., 3.):** 0 tab spacing (flush left).
  - **Roman numbered paragraphs ((i), (ii), I., II.):** 1 tab spacing (0.5 in indent).
  - **Unnumbered paragraphs:** 1 tab spacing (0.5 in indent).
  - **Headings & ORDER:** Centered with no first-line indent.
  - **Block Quotes:** Preserved with dedicated block indentation.
- **Multilingual Support:** English (Book Antiqua) and Marathi (Tiro Devanagari Marathi) support.

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   streamlit run app.py
   ```

3. (Optional) Set your Google Gemini API key in `.env` or enter it directly in the application sidebar for AI-powered parsing. Use the **Gemini model** selector to choose between Gemini 3.5 Flash Lite, Gemini 3.5 Flash, Gemini 3.5 Pro, Gemini 2.5 Flash, Gemini 2.5 Flash Lite, Gemini 2.5 Pro, and Gemini 2.0 Flash.
