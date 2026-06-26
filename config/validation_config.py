CLASSIFICATION_REVIEW_THRESHOLD = 70
OCR_CONFIDENCE_REVIEW_THRESHOLD = 75
AMOUNT_TOLERANCE = 0.02

PROCESSING_STAGES = [
    "Intake",
    "Parsing/OCR",
    "Classification",
    "Extraction",
    "Validation",
    "Review",
    "Export",
]

STATUS_OPTIONS = {
    "processing_status": [
        "Uploaded",
        "Parsed",
        "OCR Completed",
        "Extraction Completed",
        "Validation Completed",
        "Review Required",
        "Approved",
        "Rejected",
        "Exported",
    ],
    "validation_status": ["Passed", "Failed", "Warning", "Not Run"],
    "review_status": [
        "Not Required",
        "Needs Review",
        "Approved",
        "Approved with Override",
        "Rejected",
        "Follow-up",
    ],
}
