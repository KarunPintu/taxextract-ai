# TaxExtract AI

**Tagline:** Local-First Intelligent Document Processing

TaxExtract AI is a Streamlit hackathon application that demonstrates how a tax, property, or finance operations team could process business documents without sending data to cloud AI services. It uses local parsing, local OCR when Tesseract is installed, rule-based classification, regex-based extraction, validation rules, human review, audit logging, and local exports.

The app uses dummy/sample data only. Do not upload real company data to a public demo.

## What TaxExtract AI Does

TaxExtract AI helps teams:

- Upload invoices, assessments, and tax bills.
- Classify each document into Invoice, Assessment, Tax Bill, or Unknown using hybrid rules + local ML.
- Extract business fields such as invoice number, parcel ID, assessed value, total due, due dates, and installments.
- Normalize dates and money values.
- Validate document-specific business rules.
- Route risky or incomplete documents to human review.
- Allow reviewer corrections and controlled overrides.
- Export approved records to CSV, Excel, and JSON.

## Supported Document Classes

1. Invoice
2. Assessment
3. Tax Bill

## Application Sections

The sidebar has four sections:

1. **Dashboard** - operational metrics, document breakdowns, validation summaries, review queue preview, and pipeline visualization.
2. **Documents** - upload files, process samples, inspect extracted text and fields, and override document class.
3. **Insights** - document-level and portfolio-level business insights.
4. **Review & Export** - correct fields, approve, reject, follow up, approve with override, view audit history, and download exports.

## How Document Processing Works

The app follows a layered local-first architecture:

1. UI Layer - Streamlit pages and user actions.
2. Ingestion Layer - file intake and session state tracking.
3. Parsing/OCR Layer - direct PDF/DOCX text extraction and local OCR fallback.
4. Classification Layer - weighted keyword classifier.
5. Extraction Layer - class-specific field extractors.
6. Normalization Layer - amount, date, year, and text cleanup.
7. Validation Layer - reusable validation rules.
8. Insights Layer - business summaries and recommendations.
9. Human Review Layer - corrections, approvals, overrides, and follow-up.
10. Export Layer - CSV, Excel, and JSON output.
11. Audit Log Layer - document-level trace of key actions.

No cloud AI APIs or external AI APIs are used.

## Local AI/ML Layer

The classifier combines two local signals:

- A weighted keyword rules engine.
- A TF-IDF + Logistic Regression model trained on local seed examples and any user feedback added in the app.

Reviewer feedback is stored locally in:

```text
data/learning_store.json
```

This file contains class-level training examples, field-level correction examples, learned field aliases, review training events, and the local model version. It is created automatically after the first reviewer feedback or approval.

When a reviewer corrects a document class in **Documents > Local AI/ML Model Feedback**, the document text is added as a local training example. The TF-IDF + Logistic Regression classifier is rebuilt from the seed examples plus stored feedback whenever classification runs. This creates a practical human-in-the-loop learning workflow without sending documents to a cloud AI service.

When a reviewer corrects fields or approves a document, TaxExtract AI also stores field-level learning examples. Those examples teach the extractor labels such as `State Equalized Value`, `Net Taxable Value`, `Invoice Number`, or `Parcel`, so future documents with similar layouts can be mapped more accurately.

The feedback panel shows the learning-store path, number of stored examples, model version, and recent self-training events. Use **Save Learning Store** to persist immediately, **Reload Learning Store** to reload the JSON file, and **Reclassify Current Batch** to apply the current training examples to documents already loaded in the session.

The system also uses extraction evidence to avoid under-confidence. If a document extracts strong required fields and passes validation, classification confidence can be increased because the document structure supports the selected class.

For Streamlit Community Cloud, this local JSON file works during the running app instance. For a long-lived production deployment, replace the JSON store with a controlled database such as SQLite, Postgres, or an internal document-feedback service.

## Improved Extraction Layer

The extraction layer now supports multiple invoice layouts:

- Stacked label/value layouts, such as:

  ```text
  Invoice Number :
  Q200593825
  ```

- Summary-table layouts, such as:

  ```text
  Invoice Number    Invoice Date    Due Date    Subtotal    Tax Amount    Total Amount
  INV-77881         2026-04-02      2026-05-02  1,200.00    96.00         1,296.00
  ```

- Wrapped service-invoice layouts where labels and values are grouped separately, such as:

  ```text
  Invoice No:
  Invoice date:
  2023-3600009
  2023/9/30
  ...
  Amount Currenc
  330,229.12
  CNY
  Tax (670)
  19,813,75
  ```

Each extracted field includes confidence, source line, extraction method, and candidate evidence in the application.

## How to Run Locally

1. Create a virtual environment:

   ```bash
   python -m venv venv
   ```

2. Activate the virtual environment:

   Windows PowerShell:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

   macOS/Linux:

   ```bash
   source venv/bin/activate
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install Tesseract OCR locally.

5. Start the app:

   ```bash
   streamlit run app.py
   ```

## Installing Tesseract Locally

Tesseract is optional but recommended for OCR.

Windows:

- Install from the official UB Mannheim Windows builds or another trusted Tesseract installer.
- Add the Tesseract install directory to your system PATH.
- Restart your terminal after updating PATH.

macOS:

```bash
brew install tesseract
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

If Tesseract is not installed, the app will not crash. It will show:

> OCR engine is not available in this environment. This document has been routed to human review.

## Deploying on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Keep `requirements.txt` in the repo.
3. Keep `packages.txt` in the repo so Streamlit installs `tesseract-ocr`.
4. Create a new app in Streamlit Community Cloud.
5. Select `app.py` as the entry file.
6. Use dummy documents only.

## Netlify Deployment Note

TaxExtract AI is a Streamlit server application, not a static website. Netlify cannot run the live Python Streamlit server that handles uploads, parsing/OCR, review state, and exports.

The repo includes `netlify.toml` only to stop Netlify from incorrectly auto-detecting the project as Hugo and running `hugo`. If you connect this repo to Netlify, Netlify will publish a static notice page from `netlify-static/` instead of the real app.

Use one of these for the real application:

- Streamlit Community Cloud: easiest option for this project
- Render
- Railway
- Heroku or another Python web-app host

Recommended Streamlit Cloud settings:

- Repository: this repo
- Entry file: `app.py`
- Python dependencies: `requirements.txt`
- System package: `packages.txt` includes `tesseract-ocr`

## Demo Instructions

For a quick demo:

1. Start the app with `streamlit run app.py`.
2. Open the **Dashboard** to see placeholder activity.
3. Go to **Documents**.
4. Click **Load Sample Tracker Scenarios**.
5. Review the document library.
6. Open **Insights** to view portfolio and document-level insights.
7. Open **Review & Export**.
8. Correct or approve documents, including an override example.
9. Export approved records to CSV, Excel, or JSON.

Supported sample scenario names:

- `invoice_clean_01.pdf`
- `invoice_scanned_01.pdf`
- `invoice_number_missing_01.pdf`
- `invoice_total_amount_mismatch01.pdf`
- `assessment_01.pdf`
- `assessment_missing_year_01.pdf`
- `assessment_total_mismatch_01.pdf`
- `parcel_number_missing_01.pdf`
- `tax_bill_total_mismatch_01.pdf`
- `tax_bill_01.pdf`
- `tax_bill_installments_mismatch_01.pdf`
- `tax_bill_ownername_missing_01.pdf`
- `tax_bill_scanned_01.pdf`

## What Happens When Validation Fails

If required fields are missing, amounts do not reconcile, dates are out of order, OCR confidence is low, or classification confidence is low, the document is routed to human review. It is blocked from normal export until a reviewer approves it or approves it with an override.

## What Override Means

Override lets a reviewer approve a document even when validation failed or warnings remain. The reviewer must provide:

- Reviewer name
- Override reason
- Comments

The app records the override in the audit trail. Override means the human reviewer accepts responsibility for approving that record.

## Export Details

Approved records can be exported to:

- CSV
- Excel
- JSON

The Excel workbook contains:

- `Master_Output`
- `Invoice`
- `Assessment`
- `Tax_Bill`
- `Validation_Log`
- `Audit_Log`

Exports include document metadata, extracted fields, validation status, review status, override details, insights, and processing timestamp.

## Current Limitations

- Classification is rule-based, not machine-learning based.
- Extraction uses regex and label matching, so unusual layouts may need review.
- OCR quality depends on the local Tesseract installation and source image quality.
- The app stores state in Streamlit session state, so it is intended for demo and prototype use.
- No real company data should be used in this hackathon demo.

## Future Roadmap

- Add persisted storage for processed document batches.
- Add confidence scoring by field.
- Add side-by-side document image review.
- Add reviewer role management.
- Add more document classes.
- Add configurable validation rules from YAML or a database.
- Add secure on-prem deployment packaging.
- Add batch-level reconciliation and exception dashboards.

## What to Test First

Start with these scenarios:

1. `invoice_clean_01.pdf` should pass and be ready for export.
2. `invoice_total_amount_mismatch01.pdf` should route to review.
3. `assessment_missing_year_01.pdf` should route to review.
4. `tax_bill_installments_mismatch_01.pdf` should route to review.
5. `tax_bill_scanned_01.pdf` should show OCR-related review behavior.
