SUPPORTED_DOCUMENT_CLASSES = ["Invoice", "Assessment", "Tax Bill"]


DOCUMENT_SCHEMAS = {
    "Invoice": {
        "invoice_number": {"label": "Invoice Number", "required": True, "type": "text"},
        "invoice_date": {"label": "Invoice Date", "required": True, "type": "date"},
        "vendor_name": {"label": "Vendor Name", "required": True, "type": "text"},
        "client_name": {"label": "Client Name", "required": True, "type": "text"},
        "client_address": {"label": "Client Address", "required": False, "type": "text"},
        "subtotal": {"label": "Subtotal", "required": True, "type": "amount"},
        "tax_amount": {"label": "Tax Amount", "required": True, "type": "amount"},
        "total_amount": {"label": "Total Amount", "required": True, "type": "amount"},
        "currency": {"label": "Currency", "required": False, "type": "text"},
        "due_date": {"label": "Due Date", "required": False, "type": "date"},
        "line_items": {"label": "Line Items", "required": False, "type": "text"},
    },
    "Assessment": {
        "assessment_year": {"label": "Assessment Year", "required": True, "type": "year"},
        "owner_name": {"label": "Owner Name", "required": True, "type": "text"},
        "owner_address": {"label": "Owner Address", "required": False, "type": "text"},
        "city": {"label": "City", "required": False, "type": "text"},
        "state": {"label": "State", "required": False, "type": "text"},
        "zip": {"label": "ZIP", "required": False, "type": "text"},
        "parcel_id": {"label": "Parcel ID", "required": True, "type": "text"},
        "county": {"label": "County", "required": False, "type": "text"},
        "acreage": {"label": "Acreage", "required": False, "type": "amount"},
        "assessed_value": {"label": "Assessed Value", "required": True, "type": "amount"},
        "taxable_value": {"label": "Taxable Value", "required": True, "type": "amount"},
        "market_value": {"label": "Market Value", "required": True, "type": "amount"},
        "exemption_value": {"label": "Exemption Value", "required": False, "type": "amount"},
        "notice_date": {"label": "Notice Date", "required": False, "type": "date"},
        "appeal_deadline": {"label": "Appeal Deadline", "required": False, "type": "date"},
    },
    "Tax Bill": {
        "tax_bill_number": {"label": "Tax Bill Number", "required": True, "type": "text"},
        "tax_year": {"label": "Tax Year", "required": True, "type": "year"},
        "owner_name": {"label": "Owner Name", "required": True, "type": "text"},
        "owner_address": {"label": "Owner Address", "required": False, "type": "text"},
        "city": {"label": "City", "required": False, "type": "text"},
        "state": {"label": "State", "required": False, "type": "text"},
        "zip": {"label": "ZIP", "required": False, "type": "text"},
        "parcel_id": {"label": "Parcel ID", "required": True, "type": "text"},
        "county_or_jurisdiction": {"label": "County or Jurisdiction", "required": False, "type": "text"},
        "tax_amount": {"label": "Tax Amount", "required": True, "type": "amount"},
        "penalty_amount": {"label": "Penalty Amount", "required": False, "type": "amount"},
        "interest_amount": {"label": "Interest Amount", "required": False, "type": "amount"},
        "total_due": {"label": "Total Due", "required": True, "type": "amount"},
        "due_date": {"label": "Due Date", "required": False, "type": "date"},
        "assessed_value": {"label": "Assessed Value", "required": True, "type": "amount"},
        "taxable_value": {"label": "Taxable Value", "required": True, "type": "amount"},
        "market_value": {"label": "Market Value", "required": True, "type": "amount"},
        "exemption_value": {"label": "Exemption Value", "required": False, "type": "amount"},
        "installment_1": {"label": "Installment 1", "required": True, "type": "amount"},
        "installment_1_due_date": {"label": "Installment 1 Due Date", "required": True, "type": "date"},
        "installment_2": {"label": "Installment 2", "required": True, "type": "amount"},
        "installment_2_due_date": {"label": "Installment 2 Due Date", "required": True, "type": "date"},
    },
}


def get_required_fields(document_class):
    return [
        field_name
        for field_name, meta in DOCUMENT_SCHEMAS.get(document_class, {}).items()
        if meta.get("required")
    ]


def get_field_type(document_class, field_name):
    return DOCUMENT_SCHEMAS.get(document_class, {}).get(field_name, {}).get("type", "text")
