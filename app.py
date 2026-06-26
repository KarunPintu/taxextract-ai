from __future__ import annotations

import base64
import importlib
from html import escape
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List
from urllib.parse import quote

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from config.document_schemas import DOCUMENT_SCHEMAS, SUPPORTED_DOCUMENT_CLASSES
from config.validation_config import PROCESSING_STAGES
from src.classifier import classify_document
from src.demo_data import DEMO_DASHBOARD_ROWS, SAMPLE_SCENARIOS, get_sample_scenario, sample_file_names
from src.exporter import export_to_csv, export_to_excel, export_to_json, is_exportable
from src.extractor_assessment import extract_assessment_fields
from src.extractor_invoice import extract_invoice_fields
from src.extractor_tax_bill import extract_tax_bill_fields
from src.field_learning import apply_learned_field_aliases, infer_label_near_value
import src.insights as insights_engine
from src.learning_store import learning_store_path, load_learning_store, save_learning_store
from src.models import create_processed_document
from src.normalizer import normalize_fields
from src.ocr_engine import OCR_UNAVAILABLE_MESSAGE, is_ocr_available, ocr_image, ocr_images
from src.parser_docx import extract_docx_text
from src.parser_pdf import extract_pdf_text, render_pdf_pages_to_images
from src.review import apply_field_corrections, apply_reviewer_action, build_review_queue, document_needs_review
from src.session_store import document_session_path, load_document_session, save_document_session
from src.utils import add_audit_event, file_extension, file_fingerprint, new_document_id, now_iso, safe_preview
from src.validator import summarize_validation_status, validate_document


insights_engine = importlib.reload(insights_engine)
generate_document_insights = insights_engine.generate_document_insights
generate_portfolio_insights = insights_engine.generate_portfolio_insights


st.set_page_config(
    page_title="TaxExtract AI",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
            :root {
                --navy: #10233F;
                --navy-soft: #1D3557;
                --gold: #B88A2A;
                --paper: #FFFFFF;
                --mist: #F5F7FA;
                --line: #D8DEE9;
                --text: #12213A;
            }
            .block-container {
                padding-top: 1.85rem;
                padding-left: 1.25rem;
                padding-right: 1.25rem;
                padding-bottom: 1.2rem;
                max-width: 100% !important;
                width: 100% !important;
            }
            .stApp {
                background: #F4F7FB;
            }
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"],
            [data-testid="stMainBlockContainer"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            [data-testid="stSidebar"] {
                background: #10233F;
            }
            [data-testid="stSidebarHeader"] {
                height: 0 !important;
                min-height: 0 !important;
                padding: 0 !important;
            }
            [data-testid="stSidebar"] > div:first-child {
                padding: 0 !important;
            }
            [data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
            [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
                padding: 0 !important;
            }
            [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] {
                margin: 0 !important;
            }
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
                gap: 0 !important;
            }
            [data-testid="stSidebar"][aria-expanded="true"] {
                width: 215px !important;
                min-width: 215px !important;
                max-width: 215px !important;
            }
            [data-testid="stSidebar"] * {
                color: #FFFFFF !important;
            }
            [data-testid="stSidebar"][aria-expanded="true"] > div {
                width: 215px !important;
                min-width: 215px !important;
                max-width: 215px !important;
            }
            [data-testid="stSidebar"][aria-expanded="false"] {
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                overflow: hidden !important;
            }
            [data-testid="stSidebar"][aria-expanded="false"] > div {
                width: 0 !important;
                min-width: 0 !important;
                max-width: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            }
            .ryan-logo-card {
                background: #10233F;
                padding: 0;
                margin: 0;
                border-top: 0;
                border-bottom: 1px solid rgba(216, 222, 233, 0.16);
                min-height: 68px;
                height: 68px;
                box-sizing: border-box;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 100%;
            }
            .ryan-logo-image {
                display: block;
                width: 112px;
                height: auto;
            }
            .ryan-logo-wordmark {
                display: inline-flex;
                align-items: center;
                gap: 0.18rem;
                height: 36px;
                line-height: 1;
            }
            .ryan-logo-text {
                color: #FFFFFF !important;
                font-family: Arial, Helvetica, sans-serif;
                font-size: 1.34rem;
                font-style: italic;
                font-weight: 900;
                letter-spacing: 0;
            }
            .ryan-logo-chevron {
                width: 0.72rem;
                height: 0.72rem;
                border-top: 0.24rem solid currentColor;
                border-right: 0.24rem solid currentColor;
                transform: rotate(45deg);
                margin-left: 0.04rem;
            }
            .ryan-logo-chevron.white {
                color: #FFFFFF !important;
            }
            .ryan-logo-chevron.gold {
                color: #B88A2A !important;
                margin-left: -0.1rem;
            }
            .sidebar-nav {
                display: flex;
                align-items: center;
                gap: 0.58rem;
                color: #FFFFFF !important;
                text-decoration: none !important;
                padding: 0.45rem 0.58rem;
                margin: 0.16rem 0;
                border-radius: 8px;
                width: max-content;
                font-weight: 700;
                font-size: 0.86rem;
                border-left: 0;
                background: rgba(255, 255, 255, 0.06);
                white-space: nowrap;
            }
            .sidebar-nav:hover {
                background: rgba(255, 255, 255, 0.08);
            }
            .sidebar-nav.active {
                background: rgba(255, 255, 255, 0.08);
            }
            .sidebar-nav .nav-icon {
                width: 0.82rem;
                height: 0.82rem;
                flex: 0 0 0.82rem;
                border-radius: 999px;
                background: #FFFFFF;
                display: inline-block;
                color: transparent !important;
                overflow: hidden;
            }
            .sidebar-nav.active .nav-icon {
                background: #B88A2A;
            }
            [data-testid="stSidebar"] div.stButton > button {
                background: transparent;
                border: 0;
                border-left: 4px solid transparent;
                border-radius: 0;
                color: #FFFFFF !important;
                display: inline-flex;
                justify-content: flex-start !important;
                text-align: left !important;
                min-height: 2.45rem;
                padding: 0.34rem 0.78rem !important;
                width: 100% !important;
                font-size: 0.88rem;
                font-weight: 650;
                box-shadow: none;
                line-height: 1.2;
            }
            [data-testid="stSidebar"] div.stButton > button:hover {
                background: rgba(255, 255, 255, 0.08);
                border: 0;
                border-left: 4px solid rgba(184, 138, 42, 0.55);
                color: #FFFFFF !important;
            }
            [data-testid="stSidebar"] div.stButton > button[kind="primary"] {
                background: rgba(216, 222, 233, 0.17);
                border-left: 4px solid #B88A2A;
                padding-left: 0.78rem !important;
            }
            [data-testid="stSidebar"] div.stButton > button > div,
            [data-testid="stSidebar"] div.stButton > button [data-testid="stMarkdownContainer"] {
                display: block !important;
                width: 100% !important;
                text-align: left !important;
                justify-content: flex-start !important;
                align-items: flex-start !important;
            }
            [data-testid="stSidebar"] div.stButton > button p {
                color: #FFFFFF !important;
                font-size: 0.88rem;
                font-weight: 650;
                letter-spacing: 0;
                text-align: left !important;
                margin: 0 !important;
                width: 100% !important;
            }
            [data-testid="stSidebar"] div.stButton {
                margin: 0 !important;
                width: 100% !important;
            }
            [data-testid="stSidebar"] [data-testid="stElementContainer"],
            [data-testid="stSidebar"] [data-testid="element-container"] {
                margin: 0 !important;
                width: 100% !important;
            }
            .topbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                min-height: 68px;
                height: 68px;
                background: linear-gradient(90deg, #10233F 0%, #173466 58%, #B88A2A 100%);
                border-top: 0;
                margin: 0 -1.25rem 0.8rem -1.25rem;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.12);
                border-radius: 0;
                overflow: visible;
                position: sticky;
                top: 0;
                z-index: 50;
            }
            .topbar-brand {
                display: flex;
                align-items: center;
                gap: 1rem;
                padding: 0.62rem 1.8rem;
            }
            .topbar-title {
                color: #FFFFFF;
                font-size: 1.35rem;
                font-weight: 850;
                line-height: 1.15;
            }
            .topbar-subtitle {
                color: #F5E6BD;
                font-size: 0.76rem;
                margin-top: 0.25rem;
            }
            .topbar-actions {
                display: flex;
                align-items: center;
                gap: 1.05rem;
                padding: 0 1.6rem 0 1rem;
                color: #FFFFFF;
                font-size: 0.84rem;
                font-weight: 800;
                position: relative;
            }
            .topbar-action {
                color: #FFFFFF;
                white-space: nowrap;
                font-weight: 800;
                text-decoration: none;
                border: 0;
                background: transparent;
                padding: 0.35rem 0.15rem;
                cursor: pointer;
                font: inherit;
            }
            .topbar-action:hover {
                color: #F5E6BD;
            }
            .topbar-popover {
                position: fixed;
                inset: unset;
                margin: 0;
                border: 1px solid #D8DEE9;
                border-radius: 8px;
                box-shadow: 0 18px 42px rgba(16, 35, 63, 0.22);
                padding: 0.85rem 0.95rem;
                width: min(340px, calc(100vw - 2rem));
                color: #10233F;
                background: #FFFFFF;
                line-height: 1.45;
                font-size: 0.86rem;
            }
            #help-popover:popover-open {
                top: 6.7rem;
                right: 8.25rem;
            }
            #reviewer-popover:popover-open {
                top: 6.7rem;
                right: 2rem;
            }
            .topbar-popover::backdrop {
                background: transparent;
            }
            .topbar-popover-title {
                font-weight: 900;
                margin-bottom: 0.35rem;
                color: #10233F;
            }
            .topbar-popover ul {
                margin: 0.35rem 0 0 1rem;
                padding: 0;
            }
            .dashboard-title-row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 1rem;
                margin: 0.15rem 0 0.65rem 0;
            }
            .dashboard-title {
                color: #10233F;
                font-size: 1.2rem;
                font-weight: 900;
                margin: 0;
            }
            .dashboard-subtitle {
                color: #56657A;
                font-size: 0.82rem;
                margin-top: 0.18rem;
            }
            .metric-link {
                display: block;
                text-decoration: none !important;
                color: inherit !important;
                height: 100%;
            }
            .metric-link .metric-card {
                min-height: 168px;
                height: 100%;
                padding: 1rem 1.05rem;
                box-sizing: border-box;
            }
            .metric-link:hover .metric-card {
                transform: translateY(-1px);
                box-shadow: 0 12px 30px rgba(16, 35, 63, 0.11);
            }
            .dashboard-kpi-grid {
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                gap: 1rem;
                align-items: stretch;
                margin: 0.8rem 0 0.85rem 0;
            }
            .dashboard-row-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 1rem;
                align-items: stretch;
                margin-top: 0.85rem;
            }
            [data-testid="stVerticalBlockBorderWrapper"] {
                background: #FFFFFF !important;
                border: 1px solid #D8DEE9 !important;
                border-radius: 8px !important;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06) !important;
            }
            .dashboard-card {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-radius: 8px;
                padding: 0.82rem;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
                min-height: 356px;
                margin-top: 0;
                height: 100%;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .dashboard-card.compact {
                min-height: 334px;
            }
            .dashboard-card-title {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.65rem;
                color: #10233F;
                font-weight: 700;
                font-size: 0.95rem;
                margin-bottom: 0.65rem;
                min-width: 0;
            }
            .dashboard-card-title span:first-child {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .dashboard-card-link {
                color: #2F49C7 !important;
                text-decoration: none !important;
                font-size: 0.78rem;
                font-weight: 900;
                flex: 0 0 auto;
            }
            .dashboard-card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.75rem;
                margin-bottom: 0.5rem;
            }
            .dashboard-card-header .dashboard-card-title {
                margin-bottom: 0;
            }
            .recent-doc-link {
                display: flex;
                align-items: center;
                gap: 0.7rem;
                padding: 0.68rem 0;
                border-bottom: 1px solid #D9E1EC;
                color: #10233F !important;
                text-decoration: none !important;
                min-width: 0;
            }
            .recent-doc-link:hover {
                background: #F8FAFC;
            }
            .recent-doc-main {
                flex: 1;
                min-width: 0;
                overflow: hidden;
            }
            .recent-doc-title {
                display: block;
                color: #10233F;
                font-weight: 850;
                font-size: 0.86rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .recent-doc-meta {
                display: block;
                color: #667085;
                font-size: 0.78rem;
                margin-top: 0.15rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .recent-doc-status {
                flex: 0 0 7.4rem;
                display: flex;
                justify-content: center;
                min-width: 0;
            }
            .row-arrow {
                flex: 0 0 auto;
                color: #0B5DBD;
                font-size: 1.45rem;
                font-weight: 900;
                line-height: 1;
                padding-left: 0.1rem;
            }
            .dashboard-card-body {
                flex: 1;
                min-height: 0;
                min-width: 0;
                overflow: hidden;
            }
            .dashboard-card-action {
                display: block;
                border: 1px solid #C8D2E1;
                border-radius: 6px;
                color: #10233F !important;
                text-align: center;
                text-decoration: none !important;
                padding: 0.52rem 0.75rem;
                margin-top: auto;
                font-weight: 750;
                background: #FFFFFF;
            }
            .dashboard-card-action.primary {
                background: #2F49C7;
                border-color: #2F49C7;
                color: #FFFFFF !important;
                font-weight: 900;
            }
            .dashboard-card-action.disabled {
                color: #98A2B3 !important;
                background: #F8FAFC;
                pointer-events: none;
            }
            .dashboard-table {
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                font-size: 0.8rem;
                min-width: 0;
            }
            .dashboard-table th {
                text-align: left;
                color: #56657A;
                text-transform: uppercase;
                font-size: 0.62rem;
                padding: 0.5rem 0.35rem;
                border-bottom: 1px solid #D8DEE9;
                overflow-wrap: anywhere;
            }
            .dashboard-table td {
                color: #10233F;
                padding: 0.58rem 0.35rem;
                border-bottom: 1px solid #EEF2F7;
                overflow-wrap: anywhere;
            }
            .class-chart {
                height: 100%;
                min-height: 230px;
                display: flex;
                align-items: flex-end;
                gap: 0.75rem;
                padding: 0.75rem 0.45rem 0.2rem 0.45rem;
                border-top: 1px solid #E6EBF2;
                border-bottom: 1px solid #E6EBF2;
                box-sizing: border-box;
            }
            .class-bar-group {
                flex: 1;
                height: 100%;
                min-width: 0;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-end;
            }
            .class-bar {
                width: 82%;
                min-height: 8px;
                background: #B88A2A;
                border-radius: 2px 2px 0 0;
            }
            .class-count {
                color: #10233F;
                font-weight: 850;
                font-size: 0.72rem;
                margin-top: 0.25rem;
            }
            .class-label {
                color: #667085;
                font-size: 0.68rem;
                margin-top: 0.25rem;
                text-align: center;
                min-height: 2rem;
                overflow-wrap: anywhere;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-radius: 8px;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
                background: #FFFFFF;
            }
            .recent-row {
                display: flex;
                align-items: center;
                gap: 0.65rem;
                padding: 0.45rem 0;
                border-bottom: 1px solid #EEF2F7;
                min-width: 0;
                overflow: hidden;
            }
            .recent-row > div {
                min-width: 0;
                overflow: hidden;
            }
            .file-icon {
                border: 1px solid #D84D4D;
                color: #D84D4D;
                border-radius: 3px;
                font-size: 0.62rem;
                font-weight: 900;
                padding: 0.22rem 0.2rem;
            }
            .primary-action-link {
                display: block;
                background: #2F49C7;
                color: #FFFFFF !important;
                text-decoration: none !important;
                text-align: center;
                border-radius: 5px;
                padding: 0.55rem 0.75rem;
                font-weight: 900;
                margin-top: 0.75rem;
            }
            .field-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.5rem;
                margin-top: 0.65rem;
            }
            .field-tile {
                border: 1px solid #D8DEE9;
                border-radius: 5px;
                padding: 0.48rem 0.55rem;
                background: #F8FAFC;
            }
            .field-tile-label {
                color: #56657A;
                text-transform: uppercase;
                font-size: 0.64rem;
                font-weight: 900;
            }
            .field-tile-value {
                color: #10233F;
                font-size: 0.82rem;
                font-weight: 850;
                margin-top: 0.15rem;
                overflow-wrap: anywhere;
            }
            .progress-track {
                height: 0.45rem;
                background: #E7ECF5;
                border-radius: 999px;
                overflow: hidden;
                margin: 0.72rem 0 0.35rem 0;
            }
            .progress-fill {
                height: 100%;
                background: #2F49C7;
                border-radius: 999px;
            }
            .validation-mini {
                display: grid;
                grid-template-columns: minmax(120px, 0.72fr) minmax(0, 1.28fr);
                gap: 1rem;
                align-items: center;
                align-content: center;
                min-width: 0;
                min-height: 300px;
            }
            .rule-circle {
                width: 132px;
                height: 132px;
                border-radius: 50%;
                background: conic-gradient(#F2B51D 0 100%, #EEF2F7 0 100%);
                display: grid;
                place-items: center;
            }
            .rule-circle-inner {
                background: #FFFFFF;
                width: 86px;
                height: 86px;
                border-radius: 50%;
                display: grid;
                place-items: center;
                color: #2F49C7;
                font-size: 1.75rem;
                font-weight: 900;
            }
            .validation-table {
                font-size: 0.74rem;
                table-layout: fixed;
            }
            .validation-table th,
            .validation-table td {
                padding: 0.5rem 0.34rem;
                vertical-align: middle;
                overflow-wrap: normal !important;
                word-break: normal !important;
            }
            .validation-table th {
                font-size: 0.56rem;
                line-height: 1.25;
                white-space: nowrap;
            }
            .validation-table th:nth-child(1),
            .validation-table td:nth-child(1) {
                width: 42%;
                white-space: normal;
            }
            .validation-table th:not(:first-child),
            .validation-table td:not(:first-child) {
                text-align: center;
                white-space: nowrap;
            }
            .quick-export-list {
                display: grid;
                gap: 0.45rem;
            }
            .quick-export-item {
                display: block;
                border: 1px solid #D8DEE9;
                border-radius: 5px;
                color: #2F49C7 !important;
                text-align: center;
                font-weight: 900;
                padding: 0.46rem;
                text-decoration: none !important;
            }
            .quick-export-body {
                display: flex;
                flex-direction: column;
                gap: 0.58rem;
                padding-top: 0.35rem;
            }
            .quick-export-subtitle {
                color: #667085;
                font-size: 0.82rem;
                margin-bottom: 0.75rem;
            }
            .quick-export-link {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
                border: 1px solid #C8D2E1;
                border-radius: 6px;
                background: #FFFFFF;
                color: #0057B8 !important;
                text-align: center;
                text-decoration: none !important;
                min-height: 2.35rem;
                padding: 0.42rem 0.7rem;
                font-weight: 900;
                font-size: 0.86rem;
            }
            .quick-export-link:hover {
                border-color: #0057B8;
                background: #F8FAFC;
            }
            .quick-export-link.disabled {
                color: #98A2B3 !important;
                background: #F8FAFC;
                pointer-events: none;
            }
            .quick-export-link.icon-only {
                border: 0;
                min-height: 2.2rem;
                background: transparent;
                margin-top: 0.42rem;
            }
            .quick-export-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.05rem;
                min-width: 1.05rem;
                color: #0057B8;
                font-weight: 900;
                font-size: 1rem;
                line-height: 1;
            }
            .quick-export-icon svg {
                width: 1.05rem;
                height: 1.05rem;
                stroke: currentColor;
                stroke-width: 2.1;
                fill: none;
                stroke-linecap: round;
                stroke-linejoin: round;
            }
            .quick-export-icon.braces {
                font-family: Consolas, "Courier New", monospace;
                font-size: 1.05rem;
                letter-spacing: 0.02rem;
            }
            .app-header {
                background: linear-gradient(135deg, #10233F 0%, #1D3557 72%, #B88A2A 100%);
                color: white;
                padding: 1.6rem 1.8rem;
                border-radius: 10px;
                margin-bottom: 1.1rem;
                box-shadow: 0 14px 32px rgba(16, 35, 63, 0.18);
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
            }
            .app-title {
                font-size: 2.1rem;
                font-weight: 800;
                margin: 0;
                letter-spacing: 0;
            }
            .app-tagline {
                margin-top: 0.3rem;
                color: #F5E6BD;
                font-size: 1.02rem;
            }
            .app-header-copy {
                color: #FFFFFF;
                font-size: 0.92rem;
                font-weight: 650;
                max-width: 360px;
                text-align: right;
            }
            .section-card {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-radius: 8px;
                padding: 1rem;
                box-shadow: 0 4px 16px rgba(16, 35, 63, 0.06);
            }
            .metric-card {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-left: 4px solid #B88A2A;
                border-radius: 8px;
                padding: 0.95rem;
                min-height: 112px;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
                transition: transform 120ms ease, box-shadow 120ms ease;
            }
            .metric-card:hover {
                transform: translateY(-1px);
                box-shadow: 0 12px 30px rgba(16, 35, 63, 0.11);
            }
            .metric-label {
                color: #56657A;
                font-size: 0.78rem;
                text-transform: uppercase;
                font-weight: 700;
                letter-spacing: 0;
                line-height: 1.35;
            }
            .metric-value {
                color: #10233F;
                font-size: 1.65rem;
                font-weight: 800;
                margin-top: 0.3rem;
            }
            .metric-help {
                color: #667085;
                font-size: 0.85rem;
                margin-top: 0.25rem;
                line-height: 1.45;
            }
            .metric-trend {
                color: #147A4A;
                font-size: 0.78rem;
                font-weight: 750;
                margin-top: 0.5rem;
                line-height: 1.45;
            }
            .portfolio-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.85rem;
                margin-bottom: 1rem;
            }
            .portfolio-grid .metric-card {
                min-height: 138px;
                height: 100%;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                box-sizing: border-box;
            }
            .portfolio-grid .metric-value {
                font-size: 1.35rem;
                line-height: 1.18;
                overflow-wrap: anywhere;
            }
            .insight-summary-box {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-left: 4px solid #B88A2A;
                border-radius: 8px;
                padding: 1rem 1.05rem;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
                line-height: 1.58;
                white-space: pre-line;
            }
            .insight-mini-card {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-left: 4px solid #B88A2A;
                border-radius: 8px;
                padding: 1rem;
                min-height: 132px;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
                display: flex;
                flex-direction: column;
                justify-content: center;
                box-sizing: border-box;
            }
            .insight-mini-card h4 {
                color: #10233F;
                font-size: 1rem;
                margin: 0 0 0.55rem 0;
                letter-spacing: 0;
            }
            .insight-mini-card .large-value {
                color: #10233F;
                font-size: 1.45rem;
                font-weight: 850;
            }
            .status-badge {
                border-radius: 999px;
                display: inline-block;
                font-size: 0.72rem;
                font-weight: 700;
                padding: 0.2rem 0.5rem;
                white-space: nowrap;
                max-width: 108px;
                overflow: hidden;
                text-overflow: ellipsis;
                flex: 0 0 auto;
            }
            .pipeline {
                display: flex;
                gap: 0.55rem;
                flex-wrap: wrap;
                align-items: center;
            }
            .pipeline-step {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-top: 3px solid #B88A2A;
                border-radius: 8px;
                color: #10233F;
                font-weight: 750;
                padding: 0.75rem 0.85rem;
                min-width: 128px;
                text-align: center;
            }
            .pipeline-arrow {
                color: #8A94A6;
                font-weight: 800;
            }
            .small-muted {
                color: #667085;
                font-size: 0.9rem;
            }
            .stage-strip {
                display: flex;
                flex-wrap: wrap;
                gap: 0.55rem;
                margin: 0.35rem 0 0.85rem 0;
            }
            .stage-chip {
                border: 1px solid #D8DEE9;
                background: #FFFFFF;
                color: #344054;
                border-radius: 999px;
                padding: 0.38rem 0.65rem;
                font-size: 0.78rem;
                font-weight: 750;
            }
            .stage-chip.done {
                background: #E8F5EE;
                border-color: #9AD3B5;
                color: #147A4A;
            }
            .stage-chip.current {
                background: #FFF6DA;
                border-color: #E6C25D;
                color: #8A6200;
            }
            .stage-chip.blocked {
                background: #FDECEC;
                border-color: #E9A9A9;
                color: #A93434;
            }
            .stage-chip.stage-tone-0:not(.done):not(.current):not(.blocked) {
                background: #E8F5EE;
                border-color: #9AD3B5;
                color: #147A4A;
            }
            .stage-chip.stage-tone-1:not(.done):not(.current):not(.blocked) {
                background: #FFF6DA;
                border-color: #E6C25D;
                color: #8A6200;
            }
            .stage-chip.stage-tone-2:not(.done):not(.current):not(.blocked) {
                background: #EEF4FF;
                border-color: #BFD2FF;
                color: #214CA8;
            }
            .stage-chip.stage-tone-3:not(.done):not(.current):not(.blocked) {
                background: #F3EEFF;
                border-color: #D6C8FF;
                color: #5A3CA8;
            }
            .stage-chip.stage-tone-4:not(.done):not(.current):not(.blocked) {
                background: #EFF8FF;
                border-color: #B9E6FE;
                color: #026AA2;
            }
            .stage-chip.stage-tone-5:not(.done):not(.current):not(.blocked) {
                background: #FDF2FA;
                border-color: #FCCEEE;
                color: #C11574;
            }
            .stage-chip.stage-tone-6:not(.done):not(.current):not(.blocked) {
                background: #F4F3FF;
                border-color: #D9D6FE;
                color: #5925DC;
            }
            .confidence-pill {
                border-radius: 999px;
                display: inline-block;
                font-size: 0.78rem;
                font-weight: 800;
                padding: 0.18rem 0.55rem;
                border: 1px solid rgba(16, 35, 63, 0.12);
            }
            .confidence-high {
                color: #147A4A;
                background: #E8F5EE;
            }
            .confidence-medium {
                color: #8A6200;
                background: #FFF6DA;
            }
            .confidence-low {
                color: #A93434;
                background: #FDECEC;
            }
            .action-card {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-radius: 8px;
                padding: 1rem;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
                min-height: 100px;
            }
            .action-card strong {
                color: #10233F;
            }
            .recommendation-card {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-left: 4px solid #B88A2A;
                border-radius: 8px;
                padding: 0.85rem 1rem;
                margin-bottom: 0.55rem;
            }
            .split-panel {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-radius: 8px;
                padding: 1rem;
                box-shadow: 0 8px 22px rgba(16, 35, 63, 0.06);
            }
            .export-summary {
                background: #FFFFFF;
                border: 1px solid #D8DEE9;
                border-radius: 8px;
                padding: 1rem;
            }
            .doc-title {
                color: #10233F;
                font-size: 0.95rem;
                font-weight: 700;
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .doc-meta {
                color: #667085;
                font-size: 0.78rem;
                margin-top: 0.2rem;
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            div.stButton > button {
                border-radius: 6px;
                border: 1px solid #B8C4D6;
                font-weight: 700;
                background: #FFFFFF;
            }
            div.stDownloadButton > button {
                border-radius: 6px;
                font-weight: 800;
                background: #FFFFFF;
            }
            [data-testid="stSidebar"] [role="radiogroup"] label {
                background: rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                padding: 0.35rem 0.45rem;
                margin-bottom: 0.25rem;
            }
            @media (max-width: 900px) {
                #help-popover:popover-open,
                #reviewer-popover:popover-open {
                    top: 8.5rem;
                    right: 1rem;
                }
                .dashboard-kpi-grid {
                    grid-template-columns: repeat(5, minmax(0, 1fr));
                    gap: 0.7rem;
                }
                .dashboard-row-grid {
                    grid-template-columns: 1fr;
                }
                .metric-link .metric-card {
                    min-height: 154px;
                    padding: 0.85rem;
                }
                .metric-label {
                    font-size: 0.7rem;
                }
                .metric-value {
                    font-size: 1.45rem;
                }
                .metric-help,
                .metric-trend {
                    font-size: 0.72rem;
                }
                .validation-mini {
                    grid-template-columns: 1fr;
                    min-height: 300px;
                    justify-items: center;
                }
                .app-header {
                    align-items: flex-start;
                    flex-direction: column;
                }
                .app-header-copy {
                    text-align: left;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    defaults = {
        "processed_documents": [],
        "audit_log": [],
        "review_queue": [],
        "exports": [],
        "duplicate_tracking": {},
        "processed_file_keys": set(),
        "training_examples": [],
        "field_training_examples": [],
        "learned_field_aliases": {},
        "review_training_events": [],
        "model_version": 1,
        "learning_store_loaded": False,
        "learning_store_path": str(learning_store_path()),
        "learning_store_status": "",
        "document_store_loaded": False,
        "document_store_path": str(document_session_path()),
        "document_store_status": "",
        "pending_notice": None,
        "active_section": "Dashboard",
        "selected_document_id": "",
        "dashboard_current_document_id": "",
        "expand_all_document_details": False,
        "scroll_to_document_details": False,
        "scroll_to_review_selector": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if not st.session_state.learning_store_loaded:
        store, status = load_learning_store()
        st.session_state.training_examples = store.get("class_training_examples", [])
        st.session_state.field_training_examples = store.get("field_training_examples", [])
        st.session_state.learned_field_aliases = store.get("learned_field_aliases", {})
        st.session_state.review_training_events = store.get("review_training_events", [])
        st.session_state.model_version = int(store.get("model_version") or 1)
        st.session_state.learning_store_status = status
        st.session_state.learning_store_loaded = True

    if not st.session_state.document_store_loaded:
        document_store, document_status = load_document_session()
        if not st.session_state.processed_documents and document_store.get("processed_documents"):
            st.session_state.processed_documents = document_store.get("processed_documents", [])
            st.session_state.audit_log = document_store.get("audit_log", [])
            st.session_state.review_queue = document_store.get("review_queue", [])
            st.session_state.exports = document_store.get("exports", [])
            st.session_state.duplicate_tracking = document_store.get("duplicate_tracking", {})
            st.session_state.processed_file_keys = set(document_store.get("processed_file_keys", []))
        st.session_state.document_store_status = document_status
        st.session_state.document_store_loaded = True
        if st.session_state.processed_documents and not document_store.get("processed_documents"):
            persist_document_session()


def app_header() -> None:
    st.markdown(
        """
        <div class="topbar">
            <div class="topbar-brand">
                <div>
                    <div class="topbar-title">TaxExtract AI</div>
                    <div class="topbar-subtitle">Local-First Intelligent Document Processing</div>
                </div>
            </div>
            <div class="topbar-actions">
                <button class="topbar-action" popovertarget="help-popover" type="button">Help</button>
                <button class="topbar-action" popovertarget="reviewer-popover" type="button">Reviewer</button>
            </div>
        </div>
        <div id="help-popover" class="topbar-popover" popover>
            <div class="topbar-popover-title">TaxExtract AI Help</div>
            Upload invoices, assessments, and tax bills, then review extracted fields,
            validation results, confidence signals, and export readiness.
            <ul>
                <li>Use Documents to upload or inspect processed files.</li>
                <li>Use Insights to understand risks and missing fields.</li>
                <li>Use Review &amp; Export to approve, override, and download outputs.</li>
            </ul>
        </div>
        <div id="reviewer-popover" class="topbar-popover" popover>
            <div class="topbar-popover-title">Reviewer Role</div>
            Reviewers confirm extracted values, correct fields, approve clean documents,
            or apply overrides when a business exception is accepted.
            <ul>
                <li>Overrides require reviewer name, reason, and comments.</li>
                <li>Every approval and correction is captured in the audit trail.</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_tone(status: str) -> str:
    status = status or ""
    if status in ["Passed", "Approved", "Not Required", "Ready", "Exported", "Validation Completed"]:
        return "success"
    if status in ["Warning", "Needs Review", "Review Required", "Follow-up", "Blocked"]:
        return "warning"
    if status in ["Failed", "Rejected", "Unknown"]:
        return "danger"
    return "neutral"


def badge(label: str, tone: str | None = None) -> str:
    tone = tone or status_tone(label)
    colors = {
        "success": ("#E8F5EE", "#147A4A"),
        "warning": ("#FFF6DA", "#8A6200"),
        "danger": ("#FDECEC", "#A93434"),
        "info": ("#EAF1FB", "#1D4F91"),
        "neutral": ("#EEF2F7", "#344054"),
    }
    background, color = colors.get(tone, colors["neutral"])
    return (
        f"<span class='status-badge' style='background:{background};"
        f"color:{color};border:1px solid {color}22;'>{label}</span>"
    )


def metric_card_html(label: str, value: Any, help_text: str = "", trend: str = "") -> str:
    trend_html = f"<div class='metric-trend'>{escape(trend)}</div>" if trend else ""
    return clean_html(
        f"""
        <div class="metric-card">
            <div class="metric-label">{escape(label)}</div>
            <div class="metric-value">{escape(str(value))}</div>
            <div class="metric-help">{escape(help_text)}</div>
            {trend_html}
        </div>
        """
    )


def metric_card(label: str, value: str, help_text: str = "", trend: str = "") -> None:
    st.markdown(metric_card_html(label, value, help_text, trend), unsafe_allow_html=True)


SECTION_NAMES = ["Dashboard", "Documents", "Insights", "Review & Export"]
DASHBOARD_TOP_CARD_HEIGHT = 356
DASHBOARD_BOTTOM_CARD_HEIGHT = 390


def section_href(section: str) -> str:
    return f"?section={quote(section)}"


def dom_safe_id(value: str) -> str:
    safe = "".join(character if character.isalnum() else "-" for character in str(value))
    return safe.strip("-") or "target"


def sync_section_from_query() -> None:
    if "active_section" not in st.session_state:
        st.session_state.active_section = "Dashboard"
    params = st.query_params
    consumed_query = bool(params)
    section = params.get("section")
    if isinstance(section, list):
        section = section[0] if section else None
    if section in SECTION_NAMES:
        st.session_state.active_section = section

    dashboard_doc = params.get("dashboard_doc")
    if isinstance(dashboard_doc, list):
        dashboard_doc = dashboard_doc[0] if dashboard_doc else ""
    if dashboard_doc:
        st.session_state.dashboard_current_document_id = dashboard_doc
        st.session_state.selected_document_id = dashboard_doc

    selected_doc = params.get("doc")
    if isinstance(selected_doc, list):
        selected_doc = selected_doc[0] if selected_doc else ""
    review_doc = params.get("review_doc")
    if isinstance(review_doc, list):
        review_doc = review_doc[0] if review_doc else ""
    scroll_target = params.get("scroll")
    if isinstance(scroll_target, list):
        scroll_target = scroll_target[0] if scroll_target else ""
    if section == "Documents" and scroll_target == "details":
        st.session_state.scroll_to_document_details = True
        st.session_state.expand_all_document_details = False
        st.session_state.selected_document_id = selected_doc or ""
    if section == "Review & Export" and scroll_target == "review_selector":
        st.session_state.scroll_to_review_selector = True
        st.session_state.selected_document_id = review_doc or ""
    if consumed_query:
        try:
            st.query_params.clear()
        except Exception:
            pass


def sync_section_to_query(section: str) -> None:
    return None


def navigate_to(section: str, message: str = "", kind: str = "success") -> None:
    try:
        st.query_params.clear()
    except Exception:
        pass
    if section in SECTION_NAMES:
        st.session_state.active_section = section
    if message:
        set_pending_notice(message, kind=kind)
    st.rerun()


def open_upload_document_details(
    document_id: str = "",
    *,
    expand_all: bool = False,
    message: str = "Opened document details.",
) -> None:
    if document_id:
        st.session_state.selected_document_id = document_id
    else:
        st.session_state.selected_document_id = ""
    st.session_state.expand_all_document_details = expand_all
    st.session_state.scroll_to_document_details = True
    navigate_to("Documents", message)


def dashboard_document_href(document_id: str) -> str:
    return f"?section=Dashboard&dashboard_doc={quote(document_id)}"


def document_details_href(document_id: str = "") -> str:
    doc_part = f"&doc={quote(document_id)}" if document_id else ""
    return f"?section=Documents&scroll=details{doc_part}"


def review_workbench_href(document_id: str = "") -> str:
    doc_part = f"&review_doc={quote(document_id)}" if document_id else ""
    return f"?section={quote('Review & Export')}&scroll=review_selector{doc_part}"


def sidebar_nav_html(active_section: str) -> str:
    nav_items = [
        ("Dashboard", "&#9716;"),
        ("Documents", "&#9635;"),
        ("Insights", "&#9638;"),
        ("Review & Export", "&#8681;"),
    ]
    links = []
    for section, icon in nav_items:
        active_class = " active" if section == active_section else ""
        links.append(
            f"<a class='sidebar-nav{active_class}' href='{section_href(section)}' target='_self'>"
            f"<span class='nav-icon'>{icon}</span><span>{escape(section)}</span></a>"
        )
    return "".join(links)


def asset_data_uri(relative_path: str) -> str:
    path = Path(__file__).resolve().parent / relative_path
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return ""
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    return f"data:image/{mime};base64,{encoded}"


def render_sidebar() -> None:
    active_section = st.session_state.get("active_section", "Dashboard")
    logo_src = asset_data_uri("assets/ryan-logo-white.png")
    logo_html = (
        f'<img class="ryan-logo-image" src="{logo_src}" alt="Ryan logo">'
        if logo_src
        else (
            '<div class="ryan-logo-wordmark">'
            '<span class="ryan-logo-text">Ryan</span>'
            '<span class="ryan-logo-chevron white"></span>'
            '<span class="ryan-logo-chevron gold"></span>'
            '</div>'
        )
    )
    st.sidebar.markdown(
        f'<div class="ryan-logo-card">{logo_html}</div>',
        unsafe_allow_html=True,
    )
    nav_items = [
        ("Dashboard", "▦"),
        ("Documents", "▤"),
        ("Insights", "✧"),
        ("Review & Export", "⇩"),
    ]
    nav_labels = {"Documents": "Upload Documents"}
    for section, icon in nav_items:
        label = nav_labels.get(section, section)
        if st.sidebar.button(
            f"{icon}  {label}",
            key=f"sidebar_nav_{section}",
            type="primary" if section == active_section else "secondary",
            use_container_width=True,
        ):
            navigate_to(section)
    st.sidebar.markdown(
        f"""
        <div style="margin-top:1.8rem;font-size:0.82rem;opacity:0.72;">
            Local model v{st.session_state.get("model_version", 1)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def as_percent(value: Any) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if numeric <= 1:
        numeric *= 100
    return max(0, min(100, int(round(numeric))))


def confidence_badge(value: Any) -> str:
    percent = as_percent(value)
    if percent >= 95:
        tone = "confidence-high"
    elif percent >= 80:
        tone = "confidence-medium"
    else:
        tone = "confidence-low"
    return f"<span class='confidence-pill {tone}'>{percent}%</span>"


def document_average_confidence(document: Dict[str, Any]) -> int:
    metadata = document.get("extraction_metadata", {})
    values = []
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        try:
            confidence = float(meta.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        if confidence > 0:
            values.append(confidence)
    if not values:
        return as_percent(document.get("classification_confidence", 0))
    return as_percent(sum(values) / len(values))


def document_field_coverage(document: Dict[str, Any]) -> int:
    schema = DOCUMENT_SCHEMAS.get(document.get("document_class"), {})
    if not schema:
        return 0
    normalized = document.get("normalized_fields", {})
    populated = sum(1 for field_name in schema if str(normalized.get(field_name, "")).strip())
    return int(round((populated / len(schema)) * 100)) if schema else 0


def document_risk_level(document: Dict[str, Any]) -> str:
    insights = document.get("insights") or {}
    risk = insights.get("business_risk_level")
    if risk:
        return str(risk)
    if document.get("validation_status") == "Failed" or document.get("review_status") == "Rejected":
        return "High"
    if document.get("validation_status") == "Warning" or document.get("review_status") in ["Needs Review", "Follow-up"]:
        return "Medium"
    if as_percent(document.get("classification_confidence", 0)) < 70 or document_average_confidence(document) < 80:
        return "Medium"
    return "Low"


def stage_indicator_html(document: Dict[str, Any] | None = None) -> str:
    stage_states = {stage: "" for stage in PROCESSING_STAGES}
    if document is None:
        stage_states = {
            "Intake": "done",
            "Parsing/OCR": "current",
            "Classification": "",
            "Extraction": "",
            "Validation": "",
            "Review": "",
            "Export": "",
        }
    else:
        stage_states["Intake"] = "done"
        if document.get("raw_text") or document.get("processing_status") != "Uploaded":
            stage_states["Parsing/OCR"] = "done"
        if document.get("document_class") and document.get("document_class") != "Unknown":
            stage_states["Classification"] = "done"
        if document.get("extracted_fields"):
            stage_states["Extraction"] = "done"
        if document.get("validation_status") and document.get("validation_status") != "Not Run":
            stage_states["Validation"] = "done"
        review_status = document.get("review_status", "")
        export_status = document.get("export_status", "")
        if review_status in ["Not Required", "Approved", "Approved with Override"]:
            stage_states["Review"] = "done"
        elif review_status in ["Needs Review", "Follow-up"]:
            stage_states["Review"] = "current"
        elif review_status == "Rejected":
            stage_states["Review"] = "blocked"
        if export_status == "Exported":
            stage_states["Export"] = "done"
        elif export_status == "Ready":
            stage_states["Export"] = "current"
        elif export_status == "Blocked":
            stage_states["Export"] = "blocked"

    chips = "".join(
        f"<span class='stage-chip stage-tone-{index} {stage_states.get(stage, '')}'>{escape(stage)}</span>"
        for index, stage in enumerate(PROCESSING_STAGES)
    )
    return f"<div class='stage-strip'>{chips}</div>"


def field_rows_for_document(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    schema = DOCUMENT_SCHEMAS.get(document.get("document_class"), {})
    extraction_metadata = document.get("extraction_metadata", {})
    for field_name, meta in schema.items():
        field_meta = extraction_metadata.get(field_name, {})
        rows.append(
            {
                "field_name": field_name,
                "required": "Required" if meta.get("required") else "Optional",
                "extracted_value": document.get("extracted_fields", {}).get(field_name, ""),
                "normalized_value": document.get("normalized_fields", {}).get(field_name, ""),
                "confidence": as_percent(field_meta.get("confidence", 0)),
                "method": field_meta.get("extraction_method", ""),
                "source_line": field_meta.get("source_line", ""),
            }
        )
    return rows


def enhanced_document_queue_dataframe(documents: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for document in documents:
        rows.append(
            {
                "document_id": document.get("document_id", ""),
                "file_name": document.get("file_name", ""),
                "class": document.get("document_class", ""),
                "class_confidence": f"{as_percent(document.get('classification_confidence', 0))}%",
                "field_confidence": f"{document_average_confidence(document)}%",
                "field_coverage": f"{document_field_coverage(document)}%",
                "risk_level": document_risk_level(document),
                "validation": document.get("validation_status", ""),
                "review": document.get("review_status", ""),
                "export": document.get("export_status", ""),
                "processed_at": document.get("processed_at", document.get("uploaded_at", "")),
            }
        )
    return pd.DataFrame(rows)


def filter_documents_for_ui(
    documents: List[Dict[str, Any]],
    query: str,
    document_class: str,
    status: str,
) -> List[Dict[str, Any]]:
    filtered = documents
    query = query.strip().lower()
    if query:
        filtered = [
            document
            for document in filtered
            if query in document.get("file_name", "").lower()
            or query in document.get("document_id", "").lower()
            or query in str(document.get("normalized_fields", {})).lower()
        ]
    if document_class != "All":
        filtered = [document for document in filtered if document.get("document_class") == document_class]
    if status != "All":
        filtered = [
            document
            for document in filtered
            if status
            in [
                document.get("validation_status", ""),
                document.get("review_status", ""),
                document.get("export_status", ""),
                document.get("processing_status", ""),
            ]
        ]
    return filtered


def local_copilot_answer(question: str, documents: List[Dict[str, Any]]) -> str:
    question_l = question.lower()
    if not documents:
        return "Load or upload documents first. I can then explain flags, missing fields, export readiness, and review priorities."

    review_docs = [doc for doc in documents if doc.get("review_status") in ["Needs Review", "Follow-up"]]
    ready_docs = [doc for doc in documents if is_exportable(doc)]

    def doc_insights(doc: Dict[str, Any]) -> Dict[str, Any]:
        return doc.get("insights") or generate_document_insights(doc)

    def find_referenced_document() -> Dict[str, Any]:
        for doc in documents:
            file_name = doc.get("file_name", "").lower()
            document_id = doc.get("document_id", "").lower()
            if file_name and file_name in question_l:
                return doc
            if document_id and document_id in question_l:
                return doc
        selected_id = st.session_state.get("selected_document_id")
        return next(
            (doc for doc in documents if doc.get("document_id") == selected_id),
            review_docs[0] if review_docs else documents[0],
        )

    selected_doc = find_referenced_document()

    def reason_list(doc: Dict[str, Any]) -> List[str]:
        insights = doc_insights(doc)
        reasons: List[str] = []
        reasons.extend(f"missing {field.replace('_', ' ')}" for field in insights.get("missing_required_fields", []))
        reasons.extend(insights.get("failed_rules", []))
        reasons.extend(insights.get("warnings", []))
        low_fields = insights.get("low_confidence_fields", [])
        if low_fields:
            reasons.append("low confidence fields: " + ", ".join(field.replace("_", " ") for field in low_fields[:3]))
        if as_percent(doc.get("classification_confidence", 0)) < 70:
            reasons.append("low classification confidence")
        return reasons

    def exposure_value(doc: Dict[str, Any]) -> float:
        return float(doc_insights(doc).get("financial_exposure") or 0)

    def document_line(doc: Dict[str, Any]) -> str:
        insights = doc_insights(doc)
        reasons = reason_list(doc)
        reason_text = "; ".join(reasons[:3]) if reasons else "no open exception drivers"
        return (
            f"{doc.get('file_name')} | {doc.get('document_class')} | "
            f"risk {insights.get('business_risk_level', document_risk_level(doc))} | "
            f"export {insights.get('export_readiness', doc.get('export_status', 'Blocked'))} | {reason_text}"
        )

    if "missing" in question_l:
        missing_items = []
        for doc in documents:
            missing = doc_insights(doc).get("missing_required_fields", [])
            if missing:
                missing_items.append(f"{doc.get('file_name')}: {', '.join(missing)}")
        return "No required fields are currently missing." if not missing_items else "Missing-field hotspots:\n" + "\n".join(missing_items[:8])

    if any(token in question_l for token in ["priority", "next", "what should", "focus", "triage"]):
        prioritized = sorted(
            review_docs,
            key=lambda doc: (
                {"High": 0, "Medium": 1, "Low": 2}.get(doc_insights(doc).get("business_risk_level", "Medium"), 1),
                document_average_confidence(doc),
            ),
        )
        if not prioritized:
            return f"No documents are currently in the review queue. {len(ready_docs)} document(s) are ready for export."
        return "Recommended review order:\n" + "\n".join(f"{idx + 1}. {document_line(doc)}" for idx, doc in enumerate(prioritized[:6]))

    if "flag" in question_l or "why" in question_l or "review" in question_l:
        insights = doc_insights(selected_doc)
        reasons = reason_list(selected_doc)
        if not reasons:
            return (
                f"{selected_doc.get('file_name')} is not showing major exception drivers. "
                f"Current export readiness is {insights.get('export_readiness', 'Ready')}."
            )
        return (
            f"{selected_doc.get('file_name')} is flagged because: "
            + "; ".join(reasons[:5])
            + f". Suggested action: {insights.get('suggested_action', 'Review before export')}."
        )

    if any(token in question_l for token in ["validation", "failed rule", "rule", "error", "warning"]):
        counts: Dict[str, int] = {}
        for doc in documents:
            for rule in doc_insights(doc).get("failed_rules", []) + doc_insights(doc).get("warnings", []):
                counts[rule] = counts.get(rule, 0) + 1
        if not counts:
            return "No failed or warning validation rules are currently open."
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return "Top validation drivers:\n" + "\n".join(f"- {rule}: {count} document(s)" for rule, count in ranked[:8])

    if any(token in question_l for token in ["exposure", "financial", "amount", "dollar", "risk value"]):
        total_exposure = sum(exposure_value(doc) for doc in documents)
        ranked_docs = sorted(documents, key=exposure_value, reverse=True)
        lines = [
            f"Total extracted financial exposure is ${total_exposure:,.2f} across {len(documents)} document(s)."
        ]
        lines.extend(
            f"- {doc.get('file_name')}: ${exposure_value(doc):,.2f} | {doc.get('document_class')}"
            for doc in ranked_docs[:5]
            if exposure_value(doc)
        )
        return "\n".join(lines)

    if any(token in question_l for token in ["class", "classification", "type"]):
        class_counts: Dict[str, int] = {}
        low_class_docs = []
        for doc in documents:
            class_counts[doc.get("document_class", "Unknown")] = class_counts.get(doc.get("document_class", "Unknown"), 0) + 1
            if as_percent(doc.get("classification_confidence", 0)) < 70:
                low_class_docs.append(f"{doc.get('file_name')} ({as_percent(doc.get('classification_confidence', 0))}%)")
        lines = ["Class mix: " + ", ".join(f"{key}: {value}" for key, value in sorted(class_counts.items()))]
        lines.append("Low-confidence class decisions: " + (", ".join(low_class_docs[:6]) if low_class_docs else "none"))
        return "\n".join(lines)

    if "export" in question_l or "ready" in question_l:
        ready = [doc.get("file_name") for doc in ready_docs]
        if not ready:
            blockers = [document_line(doc) for doc in review_docs[:5]]
            return (
                "No documents are export-ready yet. Approve clean records or approve with override after documenting the reason.\n"
                + ("\nCurrent blockers:\n" + "\n".join(blockers) if blockers else "")
            )
        return f"{len(ready)} document(s) are export-ready: " + ", ".join(ready[:8])
    if "confidence" in question_l:
        lows = [
            f"{doc.get('file_name')} | field {document_average_confidence(doc)}% | class {as_percent(doc.get('classification_confidence', 0))}%"
            for doc in documents
            if document_average_confidence(doc) < 80 or as_percent(doc.get("classification_confidence", 0)) < 70
        ]
        return "No low-confidence documents found." if not lows else "Low-confidence documents: " + ", ".join(lows[:8])

    if any(token in question_l for token in ["summary", "portfolio", "batch", "overview"]):
        total_exposure = sum(exposure_value(doc) for doc in documents)
        return (
            f"Batch overview: {len(documents)} processed document(s), {len(review_docs)} requiring review, "
            f"{len(ready_docs)} export-ready, and ${total_exposure:,.2f} in extracted financial exposure. "
            "Use the review queue for high-risk exceptions and export only approved records."
        )

    return (
        f"I found {len(documents)} processed document(s), {len(review_docs)} requiring review, "
        f"and {sum(1 for doc in documents if is_exportable(doc))} ready for export. "
        "Ask about review priority, failed rules, missing fields, financial exposure, classification, confidence, or export readiness."
    )


def collect_audit_events() -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for document in st.session_state.processed_documents:
        events.extend(document.get("audit_events", []))
    st.session_state.audit_log = events
    return events


def persist_document_session() -> bool:
    try:
        st.session_state.review_queue = [
            document.get("document_id")
            for document in build_review_queue(st.session_state.processed_documents)
        ]
        collect_audit_events()
        success, status = save_document_session(
            {
                "processed_documents": st.session_state.get("processed_documents", []),
                "audit_log": st.session_state.get("audit_log", []),
                "review_queue": st.session_state.get("review_queue", []),
                "exports": st.session_state.get("exports", []),
                "duplicate_tracking": st.session_state.get("duplicate_tracking", {}),
                "processed_file_keys": sorted(st.session_state.get("processed_file_keys", set())),
            }
        )
        st.session_state.document_store_status = status
        return success
    except Exception as exc:
        st.session_state.document_store_status = f"Document session could not be saved: {exc}"
        return False


def current_learning_store_payload() -> Dict[str, Any]:
    return {
        "class_training_examples": st.session_state.get("training_examples", []),
        "field_training_examples": st.session_state.get("field_training_examples", []),
        "learned_field_aliases": st.session_state.get("learned_field_aliases", {}),
        "review_training_events": st.session_state.get("review_training_events", []),
        "model_version": st.session_state.get("model_version", 1),
    }


def persist_learning_store() -> bool:
    success, status = save_learning_store(current_learning_store_payload())
    st.session_state.learning_store_status = status
    return success


def reload_learning_store_from_disk() -> None:
    store, status = load_learning_store()
    st.session_state.training_examples = store.get("class_training_examples", [])
    st.session_state.field_training_examples = store.get("field_training_examples", [])
    st.session_state.learned_field_aliases = store.get("learned_field_aliases", {})
    st.session_state.review_training_events = store.get("review_training_events", [])
    st.session_state.model_version = int(store.get("model_version") or 1)
    st.session_state.learning_store_status = status


def set_pending_notice(message: str, kind: str = "success", details: str = "") -> None:
    st.session_state.pending_notice = {
        "kind": kind,
        "message": message,
        "details": details,
    }


def show_pending_notice() -> None:
    notice = st.session_state.get("pending_notice")
    if not notice:
        return
    message = notice.get("message", "")
    details = notice.get("details", "")
    if notice.get("kind") == "error":
        st.error(message)
    elif notice.get("kind") == "warning":
        st.warning(message)
    else:
        st.success(message)
    if details:
        st.caption(details)
    try:
        st.toast(message)
    except Exception:
        pass
    st.session_state.pending_notice = None


def extract_fields_for_class(document_class: str, text: str) -> Dict[str, Any]:
    if document_class == "Invoice":
        return extract_invoice_fields(text, include_metadata=True)
    if document_class == "Assessment":
        return extract_assessment_fields(text, include_metadata=True)
    if document_class == "Tax Bill":
        return extract_tax_bill_fields(text, include_metadata=True)
    return {"fields": {}, "metadata": {}, "candidates": {}, "lines": []}


def finalize_document(document: Dict[str, Any]) -> Dict[str, Any]:
    document["validation_status"] = summarize_validation_status(document["validation_results"])
    if document_needs_review(document):
        document["review_status"] = "Needs Review"
        document["processing_status"] = "Review Required"
        document["export_status"] = "Blocked"
    else:
        document["review_status"] = "Not Required"
        document["processing_status"] = "Validation Completed"
        document["export_status"] = "Ready"
    document["insights"] = generate_document_insights(document)
    document["processed_at"] = now_iso()
    return document


def recalibrate_classification_from_extraction(document: Dict[str, Any]) -> None:
    document_class = document.get("document_class", "Unknown")
    if document_class not in DOCUMENT_SCHEMAS:
        return
    required_fields = [
        field_name
        for field_name, meta in DOCUMENT_SCHEMAS.get(document_class, {}).items()
        if meta.get("required")
    ]
    normalized_fields = document.get("normalized_fields", {})
    metadata = document.get("extraction_metadata", {})
    present_required = [
        field_name
        for field_name in required_fields
        if str(normalized_fields.get(field_name, "")).strip()
    ]
    if not required_fields:
        return
    required_coverage = len(present_required) / len(required_fields)
    confidence_values = [
        float(metadata.get(field_name, {}).get("confidence") or 0)
        for field_name in present_required
    ]
    average_field_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0
    validation_status = summarize_validation_status(document.get("validation_results", []))
    current_confidence = int(document.get("classification_confidence") or 0)

    evidence_boost = 0
    if required_coverage >= 0.85 and average_field_confidence >= 0.7 and validation_status == "Passed":
        evidence_boost = 88
    elif required_coverage >= 0.7 and average_field_confidence >= 0.62 and validation_status in ["Passed", "Warning"]:
        evidence_boost = 78

    if evidence_boost > current_confidence:
        document["classification_confidence"] = evidence_boost
        document.setdefault("classification_details", {})["extraction_evidence"] = {
            "required_field_coverage": round(required_coverage, 2),
            "average_field_confidence": round(average_field_confidence, 2),
            "validation_status": validation_status,
            "confidence_before_evidence": current_confidence,
            "confidence_after_evidence": evidence_boost,
            "explanation": (
                "Classification confidence was raised because the selected document class "
                "produced strong required-field extraction and validation evidence."
            ),
        }


def parse_file_to_text(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    extension = file_extension(file_name)
    scenario = get_sample_scenario(file_name)
    text = ""
    parsing_error = ""
    ocr = {
        "required": False,
        "available": None,
        "confidence": None,
        "message": "",
    }

    if extension == "pdf":
        parsed = extract_pdf_text(file_bytes)
        text = str(parsed.get("text", ""))
        parsing_error = str(parsed.get("error", ""))
        ocr["required"] = bool(parsed.get("requires_ocr")) or bool(scenario and scenario.get("scanned"))
        if ocr["required"]:
            images = render_pdf_pages_to_images(file_bytes)
            ocr_result = ocr_images(images) if images else {
                "text": "",
                "confidence": None,
                "available": is_ocr_available(),
                "message": OCR_UNAVAILABLE_MESSAGE if not is_ocr_available() else "No renderable PDF pages were available for OCR.",
                "error": "",
            }
            if ocr_result.get("text"):
                text = str(ocr_result["text"])
            ocr["available"] = bool(ocr_result.get("available"))
            ocr["confidence"] = ocr_result.get("confidence")
            ocr["message"] = str(ocr_result.get("message", ""))
    elif extension == "docx":
        parsed = extract_docx_text(file_bytes)
        text = str(parsed.get("text", ""))
        parsing_error = str(parsed.get("error", ""))
    elif extension in ["png", "jpg", "jpeg"]:
        ocr["required"] = True
        try:
            image = Image.open(BytesIO(file_bytes)).convert("RGB")
            ocr_result = ocr_image(image)
            text = str(ocr_result.get("text", ""))
            ocr["available"] = bool(ocr_result.get("available"))
            ocr["confidence"] = ocr_result.get("confidence")
            ocr["message"] = str(ocr_result.get("message", ""))
            parsing_error = str(ocr_result.get("error", ""))
        except Exception as exc:
            parsing_error = f"Image parsing failed: {exc}"
            ocr["available"] = is_ocr_available()
            ocr["message"] = OCR_UNAVAILABLE_MESSAGE if not ocr["available"] else "Image could not be opened."
    else:
        parsing_error = "Unsupported file type."

    if scenario and not text.strip():
        text = str(scenario.get("text", ""))
    if scenario and scenario.get("scanned") and ocr["required"] and ocr["available"]:
        ocr["confidence"] = scenario.get("ocr_confidence", ocr.get("confidence"))
        if not ocr["message"]:
            ocr["message"] = "Demo scanned document processed with simulated local OCR confidence."
    if scenario and scenario.get("scanned") and not ocr["available"]:
        ocr["message"] = OCR_UNAVAILABLE_MESSAGE

    return {
        "text": text.strip(),
        "ocr": ocr,
        "parsing_error": parsing_error,
        "used_sample_fallback": bool(scenario and text.strip() == str(scenario.get("text", "")).strip()),
    }


def process_uploaded_bytes(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
    document = create_processed_document(
        document_id=new_document_id(),
        file_name=file_name,
        uploaded_at=now_iso(),
        file_type=file_extension(file_name),
    )
    add_audit_event(document, "Uploaded", "Document received by local intake pipeline.")

    parsed = parse_file_to_text(file_name, file_bytes)
    document["raw_text"] = parsed["text"]
    document["ocr"] = parsed["ocr"]
    document["processing_status"] = "Parsed"
    if parsed["parsing_error"]:
        add_audit_event(document, "Parsing Notice", parsed["parsing_error"])
    if document["ocr"].get("message"):
        add_audit_event(document, "OCR Status", document["ocr"]["message"])

    classification = classify_document(
        document["raw_text"],
        file_name=file_name,
        user_training_examples=st.session_state.get("training_examples", []),
    )
    document["document_class"] = str(classification["document_class"])
    document["classification_confidence"] = int(classification["confidence"])
    document["classification_details"] = classification
    add_audit_event(
        document,
        "Classified",
        f"Detected {document['document_class']} with {document['classification_confidence']}% confidence.",
        details=classification,
    )

    extraction_result = extract_fields_for_class(document["document_class"], document["raw_text"])
    extraction_result = apply_local_field_learning(
        extraction_result,
        document["document_class"],
        document["raw_text"],
    )
    document["extracted_fields"] = extraction_result.get("fields", {})
    document["extraction_metadata"] = extraction_result.get("metadata", {})
    document["extraction_candidates"] = extraction_result.get("candidates", {})
    document["reviewed_fields"] = dict(document["extracted_fields"])
    document["normalized_fields"] = normalize_fields(document["document_class"], document["extracted_fields"])
    document["processing_status"] = "Extraction Completed"
    add_audit_event(
        document,
        "Fields Extracted",
        "Candidate-ranked class-specific field extraction completed.",
        details={
            field_name: {
                "confidence": meta.get("confidence", 0),
                "source_line": meta.get("source_line", ""),
                "method": meta.get("extraction_method", ""),
            }
            for field_name, meta in document["extraction_metadata"].items()
        },
    )

    document["validation_results"] = validate_document(
        document["document_class"],
        document["normalized_fields"],
        existing_documents=st.session_state.processed_documents,
        current_document_id=document["document_id"],
    )
    recalibrate_classification_from_extraction(document)
    document = finalize_document(document)
    add_audit_event(
        document,
        "Validation Completed",
        f"Validation status is {document['validation_status']}.",
    )
    return document


def reprocess_with_class_override(document: Dict[str, Any], selected_class: str) -> None:
    document["document_class"] = selected_class
    document["manual_class_override"] = selected_class
    document["classification_confidence"] = max(int(document.get("classification_confidence") or 0), 70)
    extraction_result = extract_fields_for_class(selected_class, document.get("raw_text", ""))
    extraction_result = apply_local_field_learning(
        extraction_result,
        selected_class,
        document.get("raw_text", ""),
    )
    document["extracted_fields"] = extraction_result.get("fields", {})
    document["extraction_metadata"] = extraction_result.get("metadata", {})
    document["extraction_candidates"] = extraction_result.get("candidates", {})
    document["reviewed_fields"] = dict(document["extracted_fields"])
    document["normalized_fields"] = normalize_fields(selected_class, document["extracted_fields"])
    document["validation_results"] = validate_document(
        selected_class,
        document["normalized_fields"],
        existing_documents=st.session_state.processed_documents,
        current_document_id=document["document_id"],
    )
    recalibrate_classification_from_extraction(document)
    finalize_document(document)
    add_audit_event(
        document,
        "Class Override",
        f"Reviewer manually set document class to {selected_class}.",
    )
    persist_document_session()


def add_training_example(document: Dict[str, Any], label: str, source: str) -> None:
    example = {
        "label": label,
        "text": document.get("raw_text", ""),
        "source": source,
        "document_id": document.get("document_id", ""),
        "file_name": document.get("file_name", ""),
        "created_at": now_iso(),
    }
    existing_keys = {
        (item.get("label"), item.get("file_name"), item.get("source"))
        for item in st.session_state.training_examples
    }
    added = False
    if (example["label"], example["file_name"], example["source"]) not in existing_keys:
        st.session_state.training_examples.append(example)
        added = True
    if added:
        st.session_state.model_version += 1
        persist_learning_store()
    add_audit_event(
        document,
        "Classifier Training Feedback",
        f"Document text was added as a local training example for {label}.",
        details={"label": label, "model_version": st.session_state.model_version},
    )


def apply_local_field_learning(
    extraction_result: Dict[str, Any],
    document_class: str,
    raw_text: str,
) -> Dict[str, Any]:
    return apply_learned_field_aliases(
        extraction_result,
        document_class,
        raw_text,
        st.session_state.get("learned_field_aliases", {}),
    )


def capture_field_training_examples(
    document: Dict[str, Any],
    corrected_fields: Dict[str, Any],
    source: str = "human_field_review",
    include_unchanged: bool = False,
) -> int:
    document_class = document.get("document_class", "Unknown")
    raw_text = document.get("raw_text", "")
    original_fields = document.get("extracted_fields", {})
    learned_aliases = st.session_state.learned_field_aliases.setdefault(document_class, {})
    new_examples: List[Dict[str, Any]] = []
    existing_keys = {
        (
            item.get("document_class"),
            item.get("field_name"),
            item.get("corrected_value"),
            item.get("learned_label"),
            item.get("source"),
        )
        for item in st.session_state.field_training_examples
    }

    for field_name, corrected_value in corrected_fields.items():
        corrected = str(corrected_value or "").strip()
        original = str(original_fields.get(field_name, "") or "").strip()
        if not corrected or (corrected == original and not include_unchanged):
            continue
        learned_label = infer_label_near_value(raw_text, corrected)
        example = {
            "created_at": now_iso(),
            "document_id": document.get("document_id", ""),
            "file_name": document.get("file_name", ""),
            "document_class": document_class,
            "field_name": field_name,
            "original_value": original,
            "corrected_value": corrected,
            "learned_label": learned_label,
            "source": source,
        }
        example_key = (
            example["document_class"],
            example["field_name"],
            example["corrected_value"],
            example["learned_label"],
            example["source"],
        )
        if example_key not in existing_keys:
            new_examples.append(example)
            existing_keys.add(example_key)

        if learned_label:
            field_aliases = learned_aliases.setdefault(field_name, [])
            if learned_label not in field_aliases:
                field_aliases.insert(0, learned_label)
            del field_aliases[8:]

    if not new_examples:
        return 0

    st.session_state.field_training_examples.extend(new_examples)
    st.session_state.model_version += 1
    persist_learning_store()
    add_audit_event(
        document,
        "Field Training Feedback",
        f"{len(new_examples)} field correction(s) were saved as local extraction training examples.",
        details={"examples": new_examples, "model_version": st.session_state.model_version},
    )
    return len(new_examples)


def capture_approval_training(document: Dict[str, Any], action: str, reviewer_name: str = "") -> int:
    if action not in ["Approve", "Approve with Override"]:
        return 0

    before_class = len(st.session_state.training_examples)
    add_training_example(
        document,
        document.get("document_class", "Unknown"),
        source="human_approval",
    )
    class_examples_added = len(st.session_state.training_examples) - before_class

    reviewed_fields = document.get("reviewed_fields") or document.get("extracted_fields", {})
    before_fields = len(st.session_state.field_training_examples)
    capture_field_training_examples(
        document,
        reviewed_fields,
        source="human_approval_field_snapshot",
        include_unchanged=True,
    )
    field_examples_added = len(st.session_state.field_training_examples) - before_fields

    event = {
        "created_at": now_iso(),
        "document_id": document.get("document_id", ""),
        "file_name": document.get("file_name", ""),
        "document_class": document.get("document_class", "Unknown"),
        "action": action,
        "reviewer_name": reviewer_name,
        "class_examples_added": class_examples_added,
        "field_examples_added": field_examples_added,
        "model_version": st.session_state.model_version,
    }
    st.session_state.review_training_events.append(event)
    persist_learning_store()
    add_audit_event(
        document,
        "Self-Training Updated",
        "Reviewer approval was stored as local self-training feedback.",
        reviewer_name=reviewer_name,
        details=event,
    )
    return class_examples_added + field_examples_added


def reclassify_existing_documents() -> None:
    for document in st.session_state.processed_documents:
        classification = classify_document(
            document.get("raw_text", ""),
            file_name=document.get("file_name", ""),
            user_training_examples=st.session_state.get("training_examples", []),
        )
        previous_class = document.get("document_class", "Unknown")
        document["document_class"] = str(classification["document_class"])
        document["classification_confidence"] = int(classification["confidence"])
        document["classification_details"] = classification
        if previous_class != document["document_class"]:
            extraction_result = extract_fields_for_class(document["document_class"], document.get("raw_text", ""))
            extraction_result = apply_local_field_learning(
                extraction_result,
                document["document_class"],
                document.get("raw_text", ""),
            )
            document["extracted_fields"] = extraction_result.get("fields", {})
            document["extraction_metadata"] = extraction_result.get("metadata", {})
            document["extraction_candidates"] = extraction_result.get("candidates", {})
            document["reviewed_fields"] = dict(document["extracted_fields"])
        document["normalized_fields"] = normalize_fields(document["document_class"], document.get("reviewed_fields", {}))
        document["validation_results"] = validate_document(
            document["document_class"],
            document["normalized_fields"],
            existing_documents=st.session_state.processed_documents,
            current_document_id=document.get("document_id", ""),
        )
        recalibrate_classification_from_extraction(document)
        finalize_document(document)
        add_audit_event(
            document,
            "Reclassified",
            "Document was reclassified with current local training feedback.",
            details={"previous_class": previous_class, "new_class": document["document_class"]},
        )
    persist_document_session()


def mark_exported(document_ids: List[str]) -> None:
    for document in st.session_state.processed_documents:
        if document.get("document_id") in document_ids:
            document["export_status"] = "Exported"
            document["processing_status"] = "Exported"
            add_audit_event(document, "Exported", "Document was included in a local export file.")
    st.session_state.exports.append({"timestamp": now_iso(), "document_ids": document_ids})
    persist_document_session()
    set_pending_notice(f"Export completed for {len(document_ids)} approved document(s).")


def document_library_dataframe(documents: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for document in documents:
        rows.append(
            {
                "document_id": document.get("document_id", ""),
                "file_name": document.get("file_name", ""),
                "document_class": document.get("document_class", ""),
                "classification_confidence": document.get("classification_confidence", 0),
                "processing_status": document.get("processing_status", ""),
                "validation_status": document.get("validation_status", ""),
                "review_status": document.get("review_status", ""),
                "export_status": document.get("export_status", ""),
                "uploaded_at": document.get("uploaded_at", ""),
            }
        )
    return pd.DataFrame(rows)


def clean_html(html: str) -> str:
    return "\n".join(line.strip() for line in dedent(html).splitlines() if line.strip())


def render_html(html: str) -> None:
    st.markdown(clean_html(html), unsafe_allow_html=True)


def dashboard_metric_link(label: str, value: Any, help_text: str, trend: str, target_section: str) -> None:
    render_html(dashboard_metric_link_html(label, value, help_text, trend, target_section))


def dashboard_metric_link_html(label: str, value: Any, help_text: str, trend: str, target_section: str) -> str:
    trend_html = f"<div class='metric-trend'>{escape(trend)}</div>" if trend else ""
    return clean_html(f"""
        <div class="metric-link" data-target="{escape(target_section)}">
            <div class="metric-card">
                <div class="metric-label">{escape(label)}</div>
                <div class="metric-value">{escape(str(value))}</div>
                <div class="metric-help">{escape(help_text)}</div>
                {trend_html}
            </div>
        </div>
        """)


def class_breakdown_card_html(documents: List[Dict[str, Any]]) -> str:
    counts = pd.DataFrame(documents)["document_class"].value_counts().to_dict() if documents else {}
    ordered_classes = ["Assessment", "Invoice", "Tax Bill"]
    max_count = max([int(counts.get(document_class, 0)) for document_class in ordered_classes] + [1])
    bars = ""
    for document_class in ordered_classes:
        count = int(counts.get(document_class, 0))
        height = max(10, int((count / max_count) * 178)) if count else 10
        bars += clean_html(f"""
        <div class="class-bar-group">
            <div class="class-bar" style="height:{height}px;"></div>
            <div class="class-count">{count}</div>
            <div class="class-label">{escape(document_class)}</div>
        </div>
        """)
    return clean_html(f"""
    <div class="dashboard-card-title">Document Class Breakdown</div>
    <div class="dashboard-card-body">
        <div class="class-chart">{bars}</div>
    </div>
    """)


def validation_summary_card_html(documents: List[Dict[str, Any]]) -> str:
    validation_df = validation_category_summary(documents)
    total_rules = int(validation_df[["Passed", "Warnings", "Failed"]].sum().sum())
    rows = ""
    for row in validation_df.to_dict("records"):
        rows += clean_html(f"""
        <tr>
            <td>{escape(str(row.get("Rule Category", "")))}</td>
            <td>{escape(str(row.get("Passed", 0)))}</td>
            <td>{escape(str(row.get("Warnings", 0)))}</td>
            <td>{escape(str(row.get("Failed", 0)))}</td>
        </tr>
        """)
    return clean_html(f"""
    <div class="dashboard-card-title">Validation Summary</div>
    <div class="validation-mini dashboard-card-body">
        <div class="rule-circle"><div class="rule-circle-inner">{total_rules}</div></div>
        <table class="dashboard-table validation-table">
            <colgroup>
                <col style="width:46%;">
                <col style="width:18%;">
                <col style="width:18%;">
                <col style="width:18%;">
            </colgroup>
            <thead>
                <tr><th>Category</th><th>OK</th><th>Warn</th><th>Fail</th></tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """)


def quick_export_icon(kind: str) -> str:
    if kind == "json":
        return "<span class='quick-export-icon braces'>{}</span>"
    if kind == "excel":
        return clean_html("""
        <span class="quick-export-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
                <path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z"></path>
                <path d="M14 2v5h5"></path>
                <path d="M8 13h8"></path>
                <path d="M8 17h8"></path>
                <path d="M11 10v9"></path>
            </svg>
        </span>
        """)
    return clean_html("""
    <span class="quick-export-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
            <path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z"></path>
            <path d="M14 2v5h5"></path>
            <path d="M9 13h6"></path>
            <path d="M9 17h6"></path>
        </svg>
    </span>
    """)


def download_link_html(
    label: str,
    data: bytes,
    filename: str,
    mime: str,
    disabled: bool = False,
    icon: str = "",
) -> str:
    icon_html = icon
    if disabled or not data:
        return f"<span class='quick-export-link disabled'>{icon_html}<span>{escape(label)}</span></span>"
    encoded = base64.b64encode(data).decode("ascii")
    return (
        f"<a class='quick-export-link' download='{escape(filename)}' "
        f"href='data:{escape(mime)};base64,{encoded}'>{icon_html}<span>{escape(label)}</span></a>"
    )


def quick_export_card_html(exportable_documents: List[Dict[str, Any]]) -> str:
    disabled = not exportable_documents
    csv_data = export_to_csv(exportable_documents) if exportable_documents else b""
    excel_data = export_to_excel(exportable_documents) if exportable_documents else b""
    json_data = export_to_json(exportable_documents) if exportable_documents else b""
    return clean_html(f"""
    <div class="dashboard-card-title">Quick Export</div>
    <div class="dashboard-card-body quick-export-body">
        <div class="quick-export-subtitle">Export clean, structured data</div>
        {download_link_html("Export to CSV", csv_data, "taxextract_ai_export.csv", "text/csv", disabled, quick_export_icon("csv"))}
        {download_link_html("Export to Excel", excel_data, "taxextract_ai_export.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled, quick_export_icon("excel"))}
        {download_link_html("Export to JSON", json_data, "taxextract_ai_export.json", "application/json", disabled, quick_export_icon("json"))}
    </div>
    """)


def documents_for_date_window(documents: List[Dict[str, Any]], label: str) -> List[Dict[str, Any]]:
    try:
        days = int(label.split()[1])
    except (IndexError, ValueError):
        return documents
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    filtered = []
    for document in documents:
        raw_date = document.get("processed_at") or document.get("uploaded_at") or ""
        parsed_date = pd.to_datetime(raw_date, errors="coerce", utc=True)
        if pd.isna(parsed_date) or parsed_date >= cutoff:
            filtered.append(document)
    return filtered


def display_value(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def current_document_tiles(document: Dict[str, Any]) -> str:
    fields = document.get("normalized_fields", {})
    document_class = document.get("document_class", "")
    if document_class == "Invoice":
        items = [
            ("Invoice Number", fields.get("invoice_number")),
            ("Vendor", fields.get("vendor_name")),
            ("Due Date", fields.get("due_date")),
            ("Total", fields.get("total_amount")),
        ]
    elif document_class == "Assessment":
        items = [
            ("Parcel ID", fields.get("parcel_id")),
            ("Owner", fields.get("owner_name")),
            ("Year", fields.get("assessment_year")),
            ("Assessed Value", fields.get("assessed_value")),
        ]
    else:
        items = [
            ("Bill Number", fields.get("tax_bill_number")),
            ("Owner", fields.get("owner_name")),
            ("Parcel ID", fields.get("parcel_id")),
            ("Total Due", fields.get("total_due")),
        ]
    return "".join(
        f"""
        <div class="field-tile">
            <div class="field-tile-label">{escape(label)}</div>
            <div class="field-tile-value">{escape(display_value(value))}</div>
        </div>
        """
        for label, value in items
    )


def validation_category_summary(documents: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {"Rule Category": "Required Fields", "Passed": 0, "Warnings": 0, "Failed": 0},
        {"Rule Category": "Format Validation", "Passed": 0, "Warnings": 0, "Failed": 0},
        {"Rule Category": "Business Rules", "Passed": 0, "Warnings": 0, "Failed": 0},
    ]
    for document in documents:
        for result in document.get("validation_results", []):
            rule_name = str(result.get("rule_name", "")).lower()
            rule_id = str(result.get("rule_id", "")).lower()
            status = str(result.get("status", "")).lower()
            if "required" in rule_id or "blank" in rule_name:
                index = 0
            elif "numeric" in rule_id or "year" in rule_id or "date" in rule_id:
                index = 1
            else:
                index = 2
            if status == "passed":
                rows[index]["Passed"] += 1
            elif status == "warning":
                rows[index]["Warnings"] += 1
            elif status == "failed":
                rows[index]["Failed"] += 1
    return pd.DataFrame(rows)


def legacy_dashboard_section() -> None:
    documents = st.session_state.processed_documents
    display_documents = documents if documents else DEMO_DASHBOARD_ROWS
    using_demo = not documents

    if using_demo:
        st.info("Showing demo placeholder activity. Upload or load sample documents to replace these metrics.")

    processed_count = len(display_documents)
    fields_extracted = (
        sum(1 for doc in documents for value in doc.get("normalized_fields", {}).values() if str(value).strip())
        if documents
        else 34
    )
    validation_issues = sum(
        1
        for document in display_documents
        if document.get("validation_status") in ["Failed", "Warning"]
    )
    ready_for_export = sum(
        1
        for document in display_documents
        if document.get("export_status") in ["Ready", "Exported"]
        or (document.get("validation_status") == "Passed" and document.get("review_status") == "Not Required")
    )
    average_review_time = "6.4 min" if using_demo else f"{max(2.5, 8.0 - ready_for_export):.1f} min"

    metric_cols = st.columns(5)
    with metric_cols[0]:
        metric_card("Documents Processed", str(processed_count), "Local intake volume", "+ Live batch" if documents else "Demo baseline")
        if st.button("Open Documents", key="dash_open_documents", use_container_width=True):
            navigate_to("Documents", "Opened the document workbench.")
    with metric_cols[1]:
        metric_card("Fields Extracted", str(fields_extracted), "Normalized output fields", "+ Human-reviewed data")
        if st.button("View Insights", key="dash_open_insights_fields", use_container_width=True):
            navigate_to("Insights", "Opened insights for extraction quality.")
    with metric_cols[2]:
        metric_card("Validation Issues", str(validation_issues), "Failed or warning checks", "Lower is better" if validation_issues else "No open issues")
        if st.button("Review Issues", key="dash_open_review_issues", use_container_width=True):
            navigate_to("Review & Export", "Opened the review queue.")
    with metric_cols[3]:
        metric_card("Ready for Export", str(ready_for_export), "Approved local records", "+ Export-ready controls")
        if st.button("Go to Export", key="dash_open_export", use_container_width=True):
            navigate_to("Review & Export", "Opened export controls.")
    with metric_cols[4]:
        metric_card("Avg Review Time", average_review_time, "Estimated per exception", "Estimated from workflow")

    st.subheader("Pipeline")
    st.markdown(stage_indicator_html(documents[-1] if documents else None), unsafe_allow_html=True)
    pipeline_html = "<div class='pipeline' style='display:none'>"
    for index, stage in enumerate(PROCESSING_STAGES):
        pipeline_html += f"<div class='pipeline-step'>{stage}</div>"
        if index < len(PROCESSING_STAGES) - 1:
            pipeline_html += "<div class='pipeline-arrow'>→</div>"
    pipeline_html += "</div>"
    st.markdown(pipeline_html, unsafe_allow_html=True)

    current_document = documents[-1] if documents else (display_documents[0] if display_documents else {})
    if current_document:
        st.subheader("Current Document")
        st.markdown(
            f"""
            <div class="action-card">
                <div class="doc-title">{escape(current_document.get("file_name", "Demo document"))}</div>
                <div class="doc-meta">{escape(current_document.get("document_class", "Unknown"))}
                | Validation: {escape(current_document.get("validation_status", "Not Run"))}
                | Review: {escape(current_document.get("review_status", "Needs Review"))}
                | Risk: {escape(document_risk_level(current_document))}</div>
                <div style="margin-top:0.7rem;">
                    {confidence_badge(current_document.get("classification_confidence", 0))}
                    <span class="small-muted"> class confidence</span>
                    {confidence_badge(document_average_confidence(current_document))}
                    <span class="small-muted"> field confidence</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(stage_indicator_html(current_document), unsafe_allow_html=True)
        current_cols = st.columns([1, 1, 4])
        if current_cols[0].button("Open Details", key="dash_open_current", use_container_width=True):
            st.session_state.selected_document_id = current_document.get("document_id", "")
            navigate_to("Documents", "Selected the latest processed document.")
        if current_cols[1].button("Review Now", key="dash_review_current", use_container_width=True):
            st.session_state.selected_document_id = current_document.get("document_id", "")
            navigate_to("Review & Export", "Opened review for the selected document.")

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Document Class Breakdown")
        breakdown = pd.DataFrame(display_documents)["document_class"].value_counts().reset_index()
        breakdown.columns = ["Document Class", "Count"]
        st.bar_chart(breakdown.set_index("Document Class"), color="#B88A2A")

        st.subheader("Recent Documents")
        st.dataframe(enhanced_document_queue_dataframe(display_documents).head(8), use_container_width=True, hide_index=True)
        if st.button("View Document Library", key="dash_view_library", use_container_width=True):
            navigate_to("Documents", "Opened the full document library.")

    with right:
        st.subheader("Validation Summary")
        validation_summary = pd.DataFrame(display_documents)["validation_status"].value_counts().reset_index()
        validation_summary.columns = ["Status", "Documents"]
        st.dataframe(validation_summary, use_container_width=True, hide_index=True)

        st.subheader("Review Queue Preview")
        queue = [
            document for document in display_documents if document.get("review_status") in ["Needs Review", "Follow-up"]
        ]
        if queue:
            st.dataframe(
                enhanced_document_queue_dataframe(queue).head(5),
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Go to Review Queue", key="dash_go_review_queue", use_container_width=True):
                navigate_to("Review & Export", "Opened the human review queue.")
        else:
            st.success("No documents are currently waiting for human review.")


def dashboard_section_streamlit_columns() -> None:
    documents = st.session_state.processed_documents
    base_documents = documents if documents else DEMO_DASHBOARD_ROWS
    using_demo = not documents

    title_col, range_col = st.columns([4.8, 1])
    with title_col:
        st.markdown(
            """
            <div class="dashboard-title-row">
                <div>
                    <div class="dashboard-title">Dashboard Overview</div>
                    <div class="dashboard-subtitle">Track local document processing performance</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with range_col:
        date_window = st.selectbox(
            "Dashboard date range",
            ["Last 7 Days", "Last 14 Days", "Last 30 Days"],
            label_visibility="collapsed",
            key="dashboard_date_window",
        )

    display_documents = documents_for_date_window(base_documents, date_window)
    if not display_documents:
        display_documents = base_documents

    processed_count = len(display_documents)
    fields_extracted = (
        sum(1 for doc in display_documents for value in doc.get("normalized_fields", {}).values() if str(value).strip())
        if documents
        else 34
    )
    validation_issues = sum(
        1
        for document in display_documents
        if document.get("validation_status") in ["Failed", "Warning"]
    )
    ready_for_export = sum(
        1
        for document in display_documents
        if document.get("export_status") in ["Ready", "Exported"]
        or (document.get("validation_status") == "Passed" and document.get("review_status") == "Not Required")
    )
    average_review_time = "6.4 min" if using_demo else f"{max(2.5, 8.0 - ready_for_export):.1f} min"

    metric_cols = st.columns(5)
    with metric_cols[0]:
        dashboard_metric_link(
            "Documents Processed",
            processed_count,
            "Local intake volume",
            "+ Live batch" if documents else "Demo baseline",
            "Documents",
        )
    with metric_cols[1]:
        dashboard_metric_link(
            "Fields Extracted",
            fields_extracted,
            "Normalized output fields",
            "+ Human-reviewed data",
            "Insights",
        )
    with metric_cols[2]:
        dashboard_metric_link(
            "Validation Issues",
            validation_issues,
            "Failed or warning checks",
            "Lower is better" if validation_issues else "No open issues",
            "Review & Export",
        )
    with metric_cols[3]:
        dashboard_metric_link(
            "Ready for Export",
            ready_for_export,
            "Approved local records",
            "+ Export-ready controls",
            "Review & Export",
        )
    with metric_cols[4]:
        dashboard_metric_link(
            "Avg Review Time",
            average_review_time,
            "Estimated per exception",
            "Estimated from workflow",
            "Insights",
        )

    st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)
    current_document = documents[-1] if documents else (display_documents[0] if display_documents else {})

    top_row = st.columns([1, 1, 1])
    with top_row[0]:
        recent_docs = list(reversed(display_documents[-3:])) if display_documents else []
        recent_rows = ""
        for document in recent_docs:
            recent_rows += f"""
            <div class="recent-row">
                <span class="file-icon">PDF</span>
                <div style="flex:1;">
                    <div class="doc-title">{escape(display_value(document.get("file_name"), "No file"))}</div>
                    <div class="doc-meta">{escape(display_value(document.get("uploaded_at"), "Local sample"))}</div>
                </div>
                {badge(display_value(document.get("review_status"), "Ready"))}
            </div>
            """
        if not recent_rows:
            recent_rows = "<div class='small-muted'>No recent documents.</div>"
        st.markdown(
            f"""
            <div class="dashboard-card">
                <div class="dashboard-card-title">
                    <span>Recent Documents</span>
                    <span class="dashboard-card-link">View all</span>
                </div>
                {recent_rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Upload Documents", key="dash_upload_documents", use_container_width=True):
            navigate_to("Documents", "Opened the document upload area.")

    with top_row[1]:
        if current_document:
            progress = document_field_coverage(current_document)
            st.markdown(
                f"""
                <div class="dashboard-card">
                    <div class="dashboard-card-title">
                        <span>Current Document</span>
                        <span class="dashboard-card-link">Open</span>
                    </div>
                    <div class="recent-row">
                        <span class="file-icon">PDF</span>
                        <div>
                            <div class="doc-title">{escape(display_value(current_document.get("file_name"), "Demo document"))}</div>
                            <div class="doc-meta">{escape(display_value(current_document.get("document_class"), "Unknown"))}
                            | Extraction {progress}% complete</div>
                        </div>
                    </div>
                    <div class="progress-track"><div class="progress-fill" style="width:{progress}%;"></div></div>
                    <div class="field-grid">{current_document_tiles(current_document)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("View Extraction Queue", key="dash_view_extraction_queue", use_container_width=True):
                st.session_state.selected_document_id = current_document.get("document_id", "")
                navigate_to("Review & Export", "Opened the extraction queue.")
        else:
            st.markdown(
                "<div class='dashboard-card'><div class='dashboard-card-title'>Current Document</div><div class='small-muted'>No current document.</div></div>",
                unsafe_allow_html=True,
            )

    with top_row[2]:
        with st.container(border=True, height=DASHBOARD_TOP_CARD_HEIGHT):
            st.markdown("**Document Class Breakdown**")
            breakdown = pd.DataFrame(display_documents)["document_class"].value_counts().reset_index()
            breakdown.columns = ["Document Class", "Count"]
            st.bar_chart(breakdown.set_index("Document Class"), color="#B88A2A", height=206)

    st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)
    bottom_row = st.columns([1.35, 1, 0.85])
    with bottom_row[0]:
        validation_df = validation_category_summary(display_documents)
        total_rules = int(validation_df[["Passed", "Warnings", "Failed"]].sum().sum())
        st.markdown(
            f"""
            <div class="dashboard-card compact">
                <div class="dashboard-card-title">Validation Summary</div>
                <div class="validation-mini">
                    <div class="rule-circle"><div class="rule-circle-inner">{total_rules}</div></div>
                    <div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(validation_df, use_container_width=True, hide_index=True, height=132)
        st.markdown("</div></div></div>", unsafe_allow_html=True)

    with bottom_row[1]:
        queue = [
            document for document in display_documents if document.get("review_status") in ["Needs Review", "Follow-up"]
        ]
        queue_rows = ""
        for document in queue[:2]:
            queue_rows += f"""
            <div class="recent-row">
                <span class="file-icon">PDF</span>
                <div style="flex:1;">
                    <div class="doc-title">{escape(display_value(document.get("file_name"), "No file"))}</div>
                    <div class="doc-meta">{escape(display_value(document.get("uploaded_at"), "Local sample"))}</div>
                </div>
                {badge(display_value(document.get("review_status"), "Needs Review"))}
            </div>
            """
        if not queue_rows:
            queue_rows = "<div class='small-muted'>No documents currently require review.</div>"
        st.markdown(
            f"""
            <div class="dashboard-card compact">
                <div class="dashboard-card-title">
                    <span>Review Queue</span>
                    <span class="dashboard-card-link">View all</span>
                </div>
                {queue_rows}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Review Workbench", key="dash_go_review_workbench", use_container_width=True):
            navigate_to("Review & Export", "Opened the review workbench.")

    with bottom_row[2]:
        exportable_documents = [document for document in documents if is_exportable(document)]
        export_ids = [document.get("document_id", "") for document in exportable_documents]
        with st.container(border=True, height=DASHBOARD_TOP_CARD_HEIGHT):
            st.markdown("**Quick Export**")
            st.caption("Export clean, structured data")
            st.download_button(
                "Export to CSV",
                data=export_to_csv(exportable_documents) if exportable_documents else b"",
                file_name="taxextract_ai_export.csv",
                mime="text/csv",
                use_container_width=True,
                disabled=not exportable_documents,
                on_click=mark_exported,
                args=(export_ids,),
            )
            st.download_button(
                "Export to Excel",
                data=export_to_excel(exportable_documents) if exportable_documents else b"",
                file_name="taxextract_ai_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=not exportable_documents,
                on_click=mark_exported,
                args=(export_ids,),
            )
            st.download_button(
                "Export to JSON",
                data=export_to_json(exportable_documents) if exportable_documents else b"",
                file_name="taxextract_ai_export.json",
                mime="application/json",
                use_container_width=True,
                disabled=not exportable_documents,
                on_click=mark_exported,
                args=(export_ids,),
            )


def dashboard_section() -> None:
    documents = st.session_state.processed_documents
    base_documents = documents if documents else DEMO_DASHBOARD_ROWS
    using_demo = not documents

    title_col, range_col = st.columns([4.8, 1])
    with title_col:
        st.markdown(
            """
            <div class="dashboard-title-row">
                <div>
                    <div class="dashboard-title">Dashboard Overview</div>
                    <div class="dashboard-subtitle">Track local document processing performance</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with range_col:
        date_window = st.selectbox(
            "Dashboard date range",
            ["Last 7 Days", "Last 14 Days", "Last 30 Days"],
            label_visibility="collapsed",
            key="dashboard_date_window",
        )

    display_documents = documents_for_date_window(base_documents, date_window)
    if not display_documents:
        display_documents = base_documents

    processed_count = len(display_documents)
    fields_extracted = (
        sum(1 for doc in display_documents for value in doc.get("normalized_fields", {}).values() if str(value).strip())
        if documents
        else 34
    )
    validation_issues = sum(
        1
        for document in display_documents
        if document.get("validation_status") in ["Failed", "Warning"]
    )
    ready_for_export = sum(
        1
        for document in display_documents
        if document.get("export_status") in ["Ready", "Exported"]
        or (document.get("validation_status") == "Passed" and document.get("review_status") == "Not Required")
    )
    average_review_time = "6.4 min" if using_demo else f"{max(2.5, 8.0 - ready_for_export):.1f} min"

    metric_cards = [
        dashboard_metric_link_html(
            "Documents Processed",
            processed_count,
            "Local intake volume",
            "+ Live batch" if documents else "Demo baseline",
            "Documents",
        ),
        dashboard_metric_link_html(
            "Fields Extracted",
            fields_extracted,
            "Normalized output fields",
            "+ Human-reviewed data",
            "Insights",
        ),
        dashboard_metric_link_html(
            "Validation Issues",
            validation_issues,
            "Failed or warning checks",
            "Lower is better" if validation_issues else "No open issues",
            "Review & Export",
        ),
        dashboard_metric_link_html(
            "Ready for Export",
            ready_for_export,
            "Approved local records",
            "+ Export-ready controls",
            "Review & Export",
        ),
        dashboard_metric_link_html(
            "Avg Review Time",
            average_review_time,
            "Estimated per exception",
            "Estimated from workflow",
            "Insights",
        ),
    ]
    render_html(f"<div class='dashboard-kpi-grid'>{''.join(metric_cards)}</div>")

    dashboard_current_id = st.session_state.get("dashboard_current_document_id", "")
    current_document = next(
        (document for document in display_documents if document.get("document_id") == dashboard_current_id),
        None,
    )
    if not current_document:
        current_document = display_documents[-1] if display_documents else {}
    top_row = st.columns([1, 1, 1], gap="medium")

    with top_row[0]:
        recent_docs = list(reversed(display_documents[-3:])) if display_documents else []
        recent_rows = ""
        for document in recent_docs:
            document_id = document.get("document_id", "")
            recent_rows += clean_html(f"""
            <a class="recent-doc-link" href="{dashboard_document_href(document_id)}" target="_self">
                <span class="file-icon">PDF</span>
                <span class="recent-doc-main">
                    <span class="recent-doc-title">{escape(display_value(document.get("file_name"), "No file"))}</span>
                    <span class="recent-doc-meta">{escape(display_value(document.get("uploaded_at"), "Local sample"))}</span>
                </span>
                <span class="recent-doc-status">{badge(display_value(document.get("review_status"), "Ready"))}</span>
                <span class="row-arrow">&rsaquo;</span>
            </a>
            """)
        if not recent_rows:
            recent_rows = "<div class='small-muted'>No recent documents.</div>"
        with st.container(border=True, height=DASHBOARD_TOP_CARD_HEIGHT):
            st.markdown(
                f"""
                <div class="dashboard-card-header">
                    <div class="dashboard-card-title"><span>Recent Documents</span></div>
                    <a class="dashboard-card-link" href="{document_details_href()}" target="_self">View all</a>
                </div>
                <div class="dashboard-card-body">{recent_rows}</div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<a class="dashboard-card-action primary" href="{section_href("Documents")}" target="_self">Upload Documents</a>',
                unsafe_allow_html=True,
            )

    with top_row[1]:
        with st.container(border=True, height=DASHBOARD_TOP_CARD_HEIGHT):
            if current_document:
                progress = document_field_coverage(current_document)
                st.markdown(
                    f"""
                    <div class="dashboard-card-title">
                        <span>Current Document</span>
                    </div>
                    <div class="dashboard-card-body">
                        <div class="recent-row">
                            <span class="file-icon">PDF</span>
                            <div style="min-width:0;">
                                <div class="doc-title">{escape(display_value(current_document.get("file_name"), "Demo document"))}</div>
                                <div class="doc-meta">{escape(display_value(current_document.get("document_class"), "Unknown"))}
                                | Extraction {progress}% complete</div>
                            </div>
                        </div>
                        <div class="progress-track"><div class="progress-fill" style="width:{progress}%;"></div></div>
                        <div class="field-grid">{current_document_tiles(current_document)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div class="dashboard-card-title">Current Document</div>
                    <div class="dashboard-card-body"><div class="small-muted">No current document.</div></div>
                    """,
                    unsafe_allow_html=True,
                )
            open_href = document_details_href(current_document.get("document_id", "")) if current_document else section_href("Documents")
            st.markdown(
                f'<a class="dashboard-card-action primary" href="{open_href}" target="_self">Open</a>',
                unsafe_allow_html=True,
            )

    with top_row[2]:
        with st.container(border=True, height=DASHBOARD_TOP_CARD_HEIGHT):
            render_html(class_breakdown_card_html(display_documents))

    queue = [
        document for document in display_documents if document.get("review_status") in ["Needs Review", "Follow-up"]
    ]
    queue_rows = ""
    for document in queue[:2]:
        document_id = document.get("document_id", "")
        queue_rows += clean_html(f"""
        <a class="recent-doc-link" href="{review_workbench_href(document_id)}" target="_self">
            <span class="file-icon">PDF</span>
            <span class="recent-doc-main">
                <span class="recent-doc-title">{escape(display_value(document.get("file_name"), "No file"))}</span>
                <span class="recent-doc-meta">{escape(display_value(document.get("uploaded_at"), "Local sample"))}</span>
            </span>
            <span class="recent-doc-status">{badge(display_value(document.get("review_status"), "Needs Review"))}</span>
            <span class="row-arrow">&rsaquo;</span>
        </a>
        """)
    if not queue_rows:
        queue_rows = "<div class='small-muted'>No documents currently require review.</div>"

    exportable_documents = [document for document in documents if is_exportable(document)]
    export_ids = [document.get("document_id", "") for document in exportable_documents]
    bottom_row = st.columns([1, 1, 1], gap="medium")

    with bottom_row[0]:
        with st.container(border=True, height=DASHBOARD_BOTTOM_CARD_HEIGHT):
            render_html(validation_summary_card_html(display_documents))

    with bottom_row[1]:
        with st.container(border=True, height=DASHBOARD_BOTTOM_CARD_HEIGHT):
            st.markdown(
                f"""
                <div class="dashboard-card-title">
                    <span>Review Queue</span>
                </div>
                <div class="dashboard-card-body">{queue_rows}</div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<a class="dashboard-card-action primary" href="{review_workbench_href()}" '
                'target="_self" title="Select document from the dropdown">Go to Review Workbench</a>',
                unsafe_allow_html=True,
            )

    with bottom_row[2]:
        with st.container(border=True, height=DASHBOARD_BOTTOM_CARD_HEIGHT):
            render_html(quick_export_card_html(exportable_documents))


def documents_section() -> None:
    st.subheader("Upload Documents")
    st.caption("Accepted formats: PDF, DOCX, PNG, JPG, JPEG. Processing stays local.")
    st.markdown(stage_indicator_html(None), unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Upload invoice, assessment, or tax bill samples",
        type=["pdf", "docx", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help="Select one or more local invoice, assessment, or tax bill files. Processing stays on this machine.",
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.getvalue()
            fingerprint = file_fingerprint(uploaded_file.name, file_bytes)
            if fingerprint in st.session_state.processed_file_keys:
                continue
            with st.status(f"Processing {uploaded_file.name}", expanded=False) as status:
                try:
                    status.write("Intake completed")
                    document = process_uploaded_bytes(uploaded_file.name, file_bytes)
                    status.write("Parsing/OCR completed")
                    status.write("Classification completed")
                    status.write("Extraction completed")
                    status.write("Validation completed")
                    st.session_state.processed_documents.append(document)
                    st.session_state.processed_file_keys.add(fingerprint)
                    persist_document_session()
                    set_pending_notice(
                        f"{uploaded_file.name} was processed and added to the library.",
                        details=st.session_state.document_store_status,
                    )
                    status.update(label=f"Processed {uploaded_file.name}", state="complete")
                except Exception as exc:
                    status.update(label=f"Could not process {uploaded_file.name}", state="error")
                    st.error(f"{uploaded_file.name} could not be processed. It has not been added to the library.")
                    st.caption(str(exc))

    if not st.session_state.processed_documents:
        st.info("No uploaded documents yet. Upload invoice, assessment, or tax bill samples to begin.")
        return

    with st.expander("Local AI/ML Model Feedback", expanded=False):
        st.write(
            "Correct a document class or reviewed fields to add local training examples. "
            "The classifier retrains in-session, and field corrections become reusable extraction hints without cloud APIs."
        )
        model_cols = st.columns([2, 1, 1, 1])
        document_map = {
            f"{doc['document_id']} | {doc['file_name']} | current: {doc['document_class']}": doc
            for doc in st.session_state.processed_documents
        }
        selected_training_label = model_cols[0].selectbox(
            "Training document",
            list(document_map.keys()),
            key="training_document_select",
        )
        corrected_class = model_cols[1].selectbox(
            "Correct class",
            SUPPORTED_DOCUMENT_CLASSES,
            key="training_correct_class",
        )
        with model_cols[2]:
            st.metric("Class Examples", len(st.session_state.training_examples))
        with model_cols[3]:
            st.metric("Field Examples", len(st.session_state.field_training_examples))
            st.caption(f"Model version {st.session_state.model_version}")
        selected_training_document = document_map[selected_training_label]
        train_cols = st.columns(4)
        if train_cols[0].button("Add Training Example", use_container_width=True):
            add_training_example(
                selected_training_document,
                corrected_class,
                source="manual_feedback",
            )
            set_pending_notice(
                f"Added local training example for {corrected_class}.",
                details=st.session_state.learning_store_status,
            )
            st.rerun()
        if train_cols[1].button("Reclassify Current Batch", use_container_width=True):
            reclassify_existing_documents()
            set_pending_notice("Reclassified current documents using local training feedback.")
            st.rerun()
        if train_cols[2].button("Save Learning Store", use_container_width=True):
            persist_learning_store()
            set_pending_notice("Learning store saved.", details=st.session_state.learning_store_status)
            st.rerun()
        if train_cols[3].button("Reload Learning Store", use_container_width=True):
            reload_learning_store_from_disk()
            set_pending_notice("Learning store reloaded.", details=st.session_state.learning_store_status)
            st.rerun()
        if st.session_state.training_examples:
            st.caption("Recent class-level examples")
            st.dataframe(
                pd.DataFrame(st.session_state.training_examples)[
                    ["created_at", "label", "file_name", "source"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        if st.session_state.review_training_events:
            st.caption("Recent self-training review events")
            st.dataframe(
                pd.DataFrame(st.session_state.review_training_events)[
                    [
                        "created_at",
                        "action",
                        "document_class",
                        "file_name",
                        "class_examples_added",
                        "field_examples_added",
                        "model_version",
                    ]
                ].tail(12),
                use_container_width=True,
                hide_index=True,
            )
        if st.session_state.field_training_examples:
            st.caption("Recent field-level examples")
            st.dataframe(
                pd.DataFrame(st.session_state.field_training_examples)[
                    ["created_at", "document_class", "field_name", "corrected_value", "learned_label", "file_name"]
                ].tail(12),
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("Extraction Queue")
    filter_cols = st.columns([2, 1, 1], vertical_alignment="bottom")
    search_query = filter_cols[0].text_input(
        "Search queue",
        placeholder="Search file name, document ID, or extracted values",
        label_visibility="collapsed",
    )
    class_filter = filter_cols[1].selectbox("Class filter", ["All"] + SUPPORTED_DOCUMENT_CLASSES)
    status_filter = filter_cols[2].selectbox(
        "Status filter",
        ["All", "Passed", "Failed", "Warning", "Needs Review", "Approved", "Ready", "Blocked", "Exported"],
    )
    filtered_documents = filter_documents_for_ui(
        st.session_state.processed_documents,
        search_query,
        class_filter,
        status_filter,
    )
    queue_cols = st.columns([1, 1, 1, 1])
    queue_cols[0].metric("Total Documents", len(filtered_documents))
    queue_cols[1].metric("Ready", sum(1 for doc in filtered_documents if is_exportable(doc)))
    queue_cols[2].metric("Needs Review", sum(1 for doc in filtered_documents if doc.get("review_status") in ["Needs Review", "Follow-up"]))
    queue_cols[3].metric("Avg Field Confidence", f"{int(round(sum(document_average_confidence(doc) for doc in filtered_documents) / len(filtered_documents)))}%" if filtered_documents else "0%")
    st.dataframe(enhanced_document_queue_dataframe(filtered_documents), use_container_width=True, hide_index=True)

    st.markdown('<div id="document-details-section" style="scroll-margin-top:90px;"></div>', unsafe_allow_html=True)
    document_detail_scroll_target = ""
    if st.session_state.get("scroll_to_document_details"):
        selected_detail_id = st.session_state.get("selected_document_id", "")
        document_detail_scroll_target = (
            f"document-detail-{dom_safe_id(selected_detail_id)}"
            if selected_detail_id
            else "document-details-section"
        )
    st.subheader("Document Details")
    ordered_documents = filtered_documents or st.session_state.processed_documents
    expand_all_details = bool(st.session_state.get("expand_all_document_details", False))
    for document in ordered_documents:
        detail_marker_id = f"document-detail-{dom_safe_id(document.get('document_id', ''))}"
        st.markdown(
            f'<div id="{detail_marker_id}" style="scroll-margin-top:105px;height:0;"></div>',
            unsafe_allow_html=True,
        )
        title = f"{document['document_id']} | {document['file_name']}"
        should_expand = expand_all_details or document.get("document_id") == st.session_state.get("selected_document_id")
        with st.expander(title, expanded=should_expand):
            st.markdown(stage_indicator_html(document), unsafe_allow_html=True)
            top_cols = st.columns([1, 1, 1, 1, 1])
            top_cols[0].markdown(badge(document.get("document_class", "Unknown"), "info"), unsafe_allow_html=True)
            top_cols[1].markdown(badge(document.get("validation_status", "Not Run")), unsafe_allow_html=True)
            top_cols[2].markdown(badge(document.get("review_status", "Needs Review")), unsafe_allow_html=True)
            top_cols[3].markdown(badge(document.get("export_status", "Not Exported")), unsafe_allow_html=True)
            top_cols[4].markdown(confidence_badge(document_average_confidence(document)), unsafe_allow_html=True)

            override_col, review_col = st.columns([2, 1])
            with override_col:
                current_class = document.get("document_class")
                default_index = SUPPORTED_DOCUMENT_CLASSES.index(current_class) if current_class in SUPPORTED_DOCUMENT_CLASSES else 0
                selected_class = st.selectbox(
                    "Manual document class override",
                    SUPPORTED_DOCUMENT_CLASSES,
                    index=default_index,
                    key=f"class_override_{document['document_id']}",
                )
                if st.button("Apply Class Override", key=f"apply_class_{document['document_id']}"):
                    reprocess_with_class_override(document, selected_class)
                    persist_document_session()
                    set_pending_notice(f"Document class updated to {selected_class} and validations were re-run.")
                    st.rerun()
            with review_col:
                manual_review = st.checkbox(
                    "Route to human review",
                    value=bool(document.get("manual_review_requested")),
                    key=f"manual_review_{document['document_id']}",
                )
                if manual_review != bool(document.get("manual_review_requested")):
                    document["manual_review_requested"] = manual_review
                    finalize_document(document)
                    add_audit_event(
                        document,
                        "Manual Review Routing",
                        "Document was manually routed to review." if manual_review else "Manual review flag was removed.",
                    )
                    persist_document_session()
                    st.rerun()

            detail_tabs = st.tabs(["Extracted Fields", "Raw Text Preview", "Classification"])
            with detail_tabs[0]:
                field_df = pd.DataFrame(field_rows_for_document(document))
                st.dataframe(field_df, use_container_width=True, hide_index=True)
            with detail_tabs[1]:
                st.text_area(
                    "Raw extracted text",
                    safe_preview(document.get("raw_text", "")),
                    height=260,
                    key=f"raw_text_{document['document_id']}",
                    disabled=True,
                )
            with detail_tabs[2]:
                st.json(document.get("classification_details", {}))

    if document_detail_scroll_target:
        components.html(
            f"""
            <script>
            setTimeout(() => {{
                const marker =
                    window.parent.document.getElementById("{document_detail_scroll_target}") ||
                    window.parent.document.getElementById("document-details-section");
                if (marker) {{
                    marker.scrollIntoView({{ behavior: "smooth", block: "start" }});
                }}
            }}, 700);
            </script>
            """,
            height=0,
        )
        st.session_state.scroll_to_document_details = False


def insights_section() -> None:
    documents = st.session_state.processed_documents
    if not documents:
        st.info("Load or upload documents to generate portfolio and document-level insights.")
        return

    for document in documents:
        document["insights"] = generate_document_insights(document)

    portfolio = generate_portfolio_insights(documents)
    passed_validation_count = sum(
        1
        for document in documents
        if document.get("validation_status") == "Passed"
        or (
            document.get("validation_results")
            and
            document.get("validation_status") != "Failed"
            and not any(
                result.get("status") == "failed"
                for result in document.get("validation_results", [])
            )
        )
    )
    st.subheader("Portfolio Insights")
    portfolio_cards = [
        metric_card_html("Manual Time Saved", portfolio["estimated_manual_time_saved"], "Estimated reviewer effort avoided"),
        metric_card_html("Documents Requiring Review", str(portfolio["documents_requiring_review"]), "Human queue"),
        metric_card_html("Highest Exception Class", portfolio["class_with_highest_exception_rate"], "Portfolio risk"),
        metric_card_html("Most Common Failed Validation Rule", portfolio["most_common_failed_rule"], "Exception pattern"),
        metric_card_html("Documents Passed the Validations", str(passed_validation_count), "Validation clean"),
        metric_card_html("Missing Field Hotspot", portfolio["fields_most_commonly_missing"], "Data quality"),
    ]
    render_html(f"<div class='portfolio-grid'>{''.join(portfolio_cards)}</div>")

    st.subheader("Interactive Analytics")
    chart_cols = st.columns(3)
    with chart_cols[0]:
        st.markdown("**Validation Status**")
        validation_chart = pd.DataFrame(documents)["validation_status"].value_counts().reset_index()
        validation_chart.columns = ["Status", "Documents"]
        st.bar_chart(validation_chart.set_index("Status"), color="#B88A2A")
    with chart_cols[1]:
        st.markdown("**Extraction Confidence**")
        confidence_chart = pd.DataFrame(
            {
                "Document": [doc.get("file_name", "")[:28] for doc in documents],
                "Confidence": [document_average_confidence(doc) for doc in documents],
            }
        )
        st.bar_chart(confidence_chart.set_index("Document"), color="#1D3557")
    with chart_cols[2]:
        st.markdown("**Risk Level**")
        risk_chart = pd.DataFrame({"Risk": [document_risk_level(doc) for doc in documents]}).value_counts().reset_index()
        risk_chart.columns = ["Risk", "Documents"]
        st.bar_chart(risk_chart.set_index("Risk"), color="#B88A2A")

    st.subheader("Actionable Recommendations")
    review_docs = [doc for doc in documents if doc.get("review_status") in ["Needs Review", "Follow-up"]]
    low_confidence_docs = [
        doc for doc in documents
        if document_average_confidence(doc) < 80 or as_percent(doc.get("classification_confidence", 0)) < 70
    ]
    ready_docs = [doc for doc in documents if is_exportable(doc)]
    rec_cols = st.columns(3)
    with rec_cols[0]:
        st.markdown(
            f"""
            <div class="recommendation-card">
                <strong>Review exceptions</strong><br>
                <span class="small-muted">{len(review_docs)} document(s) need reviewer attention.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open Review Queue", key="insights_open_review", use_container_width=True):
            navigate_to("Review & Export", "Opened review queue from insights.")
    with rec_cols[1]:
        st.markdown(
            f"""
            <div class="recommendation-card">
                <strong>Check confidence</strong><br>
                <span class="small-muted">{len(low_confidence_docs)} document(s) have low extraction or class confidence.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open Document Details", key="insights_open_documents", use_container_width=True):
            navigate_to("Documents", "Opened document details from insights.")
    with rec_cols[2]:
        st.markdown(
            f"""
            <div class="recommendation-card">
                <strong>Export approved records</strong><br>
                <span class="small-muted">{len(ready_docs)} document(s) are ready for controlled export.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Open Export", key="insights_open_export", use_container_width=True):
            navigate_to("Review & Export", "Opened export controls from insights.")

    with st.expander("Local AI Copilot", expanded=True):
        st.caption(
            "Local-only assistant for batch triage. It can explain review priority, failed rules, "
            "missing fields, financial exposure, classification, confidence, and export readiness."
        )
        question = st.text_input(
            "Ask about this batch",
            placeholder="Example: What should I review first? What is the financial exposure? Which validations failed?",
        )
        if question:
            st.info(local_copilot_answer(question, documents))

    st.subheader("Document Insights")
    document_map = {f"{doc['document_id']} | {doc['file_name']}": doc for doc in documents}
    selected_label = st.selectbox("Select processed document", list(document_map.keys()))
    document = document_map[selected_label]
    insights = generate_document_insights(document)
    document["insights"] = insights

    summary_cols = st.columns(4)
    summary_cols[0].metric("Detected Class", document.get("document_class", "Unknown"))
    summary_cols[1].metric("Extraction Quality", f"{insights.get('extraction_quality', 0)}%")
    summary_cols[2].metric("Risk Level", insights.get("business_risk_level", "Low"))
    summary_cols[3].metric("Export Readiness", insights.get("export_readiness", "Needs Review"))

    st.markdown("#### Summary")
    render_html(
        f"<div class='insight-summary-box'>{escape(insights.get('summary', 'No summary available.'))}</div>"
    )

    left, right = st.columns(2)
    with left:
        st.markdown("#### Missing Required Fields")
        missing = insights.get("missing_required_fields", [])
        st.write(", ".join(missing) if missing else "No missing required fields.")

        st.markdown("#### Failed Validation Rules")
        failed = insights.get("failed_rules", [])
        st.write("\n".join(f"- {rule}" for rule in failed) if failed else "No failed validation rules.")

    with right:
        st.markdown("#### Warning Rules")
        warnings = insights.get("warnings", [])
        st.write("\n".join(f"- {rule}" for rule in warnings) if warnings else "No warning rules.")

        st.markdown("#### Suggested Next Action")
        st.info(insights.get("suggested_action", "Ready for export"))

    drivers = insights.get("exception_drivers", [])
    driver_text = ", ".join(driver.replace("_", " ") for driver in drivers) if drivers else "No exception drivers detected."
    exposure_cols = st.columns(2)
    with exposure_cols[0]:
        render_html(
            f"""
            <div class="insight-mini-card">
                <h4>Exception Drivers</h4>
                <div>{escape(driver_text)}</div>
            </div>
            """
        )
    with exposure_cols[1]:
        render_html(
            f"""
            <div class="insight-mini-card">
                <h4>Financial Exposure</h4>
                <div class="large-value">{escape(insights.get("financial_exposure_display", "Not estimated"))}</div>
                <div class="small-muted">Based on extracted total, tax due, or assessed value fields.</div>
            </div>
            """
        )

    enterprise_cols = st.columns(2)
    with enterprise_cols[0]:
        st.markdown("#### Automation Decision")
        decision = insights.get("automation_decision", "Human-in-the-loop review required")
        if insights.get("export_readiness") == "Ready":
            st.success(decision)
        else:
            st.warning(decision)
    with enterprise_cols[1]:
        st.markdown("#### Control Recommendations")
        for recommendation in insights.get("control_recommendations", []):
            st.write(f"- {recommendation}")

    with st.expander("Evidence Trail"):
        evidence = insights.get("evidence_trail", [])
        if evidence:
            st.dataframe(pd.DataFrame(evidence), use_container_width=True, hide_index=True)
        else:
            st.write("No field-level evidence was captured.")

    with st.expander("Confidence Summary"):
        st.json(insights.get("confidence_summary", {}))


def review_export_section() -> None:
    documents = st.session_state.processed_documents
    if not documents:
        st.info("Load or upload documents before using review and export.")
        return

    review_queue = build_review_queue(documents)
    st.session_state.review_queue = [document.get("document_id") for document in review_queue]

    review_tab, export_tab, audit_tab = st.tabs(["Review Queue", "Export", "Audit Trail"])

    with review_tab:
        st.subheader("Human Review Queue")
        if not review_queue:
            st.success("No documents currently require human review.")
        else:
            queue_df = enhanced_document_queue_dataframe(review_queue)
            st.dataframe(queue_df, use_container_width=True, hide_index=True)

            st.markdown('<div id="review-selector-section" style="scroll-margin-top:95px;"></div>', unsafe_allow_html=True)
            if st.session_state.get("scroll_to_review_selector"):
                components.html(
                    """
                    <script>
                    setTimeout(() => {
                        const marker = window.parent.document.getElementById("review-selector-section");
                        if (marker) {
                            marker.scrollIntoView({ behavior: "smooth", block: "start" });
                        }
                    }, 450);
                    </script>
                    """,
                    height=0,
                )
                st.session_state.scroll_to_review_selector = False

            document_map = {f"{doc['document_id']} | {doc['file_name']}": doc for doc in review_queue}
            placeholder_label = "Select document from the dropdown"
            labels = [placeholder_label] + list(document_map.keys())
            selected_id = st.session_state.get("selected_document_id", "")
            default_index = next(
                (index for index, label in enumerate(labels) if selected_id and selected_id in label),
                0,
            )
            selected_label = st.selectbox(
                "Select document to review",
                labels,
                index=default_index,
                help="Select document from the dropdown",
            )
            document = document_map.get(selected_label)
            if not document:
                st.session_state.selected_document_id = ""
                st.info("Select document from the dropdown to open the review workbench.")
            else:
                st.session_state.selected_document_id = document.get("document_id", "")
                st.markdown(stage_indicator_html(document), unsafe_allow_html=True)

                st.markdown("#### Review Workbench")
                preview_col, fields_col = st.columns([1, 1.35])
                with preview_col:
                    st.markdown("**Source Preview**")
                    st.text_area(
                        "Raw extracted text",
                        safe_preview(document.get("raw_text", ""), limit=8000),
                        height=410,
                        key=f"review_raw_{document['document_id']}",
                        disabled=True,
                        label_visibility="collapsed",
                    )
                    st.markdown("**Exception Context**")
                    insights = document.get("insights") or {}
                    missing = insights.get("missing_required_fields", [])
                    failed = insights.get("failed_rules", [])
                    warnings = insights.get("warnings", [])
                    if missing:
                        st.warning("Missing required fields: " + ", ".join(missing))
                    if failed:
                        st.error("Failed rules: " + "; ".join(failed[:4]))
                    if warnings:
                        st.warning("Warning rules: " + "; ".join(warnings[:4]))
                    if not missing and not failed and not warnings:
                        st.success("No major exceptions are currently blocking this record.")

                with fields_col:
                    st.markdown("**Editable Extracted Fields**")
                    schema = DOCUMENT_SCHEMAS.get(document.get("document_class"), {})
                    rows = []
                    reviewed_fields = document.get("reviewed_fields") or document.get("extracted_fields", {})
                    extraction_metadata = document.get("extraction_metadata", {})
                    for field_name, meta in schema.items():
                        field_meta = extraction_metadata.get(field_name, {})
                        rows.append(
                            {
                                "field_name": field_name,
                                "status": "Required" if meta.get("required") else "Optional",
                                "original_value": document.get("extracted_fields", {}).get(field_name, ""),
                                "reviewed_value": reviewed_fields.get(field_name, ""),
                                "confidence": as_percent(field_meta.get("confidence", 0)),
                                "source_line": field_meta.get("source_line", ""),
                            }
                        )
                    edited = st.data_editor(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                        disabled=["field_name", "status", "original_value", "confidence", "source_line"],
                        key=f"field_editor_{document['document_id']}",
                    )
                    if st.button("Save Field Corrections", key=f"save_fields_{document['document_id']}", use_container_width=True):
                        corrected_fields = {
                            row["field_name"]: row["reviewed_value"] for row in edited.to_dict("records")
                        }
                        learned_count = capture_field_training_examples(document, corrected_fields)
                        apply_field_corrections(document, corrected_fields, existing_documents=documents)
                        finalize_document(document)
                        persist_document_session()
                        detail = (
                            f"{learned_count} local field training example(s) captured."
                            if learned_count
                            else "No new training examples were needed."
                        )
                        set_pending_notice("Field corrections saved and validations were re-run.", details=detail)
                        st.rerun()

                st.markdown("#### Validation Results")
                validation_df = pd.DataFrame(document.get("validation_results", []))
                if not validation_df.empty:
                    validation_df["field_names"] = validation_df["field_names"].apply(lambda fields: ", ".join(fields))
                    st.dataframe(validation_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No validation results found.")

                action = st.radio(
                    "Reviewer action",
                    ["Approve", "Reject", "Mark for Follow-up", "Approve with Override"],
                    horizontal=True,
                    key=f"review_action_{document['document_id']}",
                )
                reviewer_name = st.text_input("Reviewer name", key=f"reviewer_{document['document_id']}")
                comments = st.text_area("Reviewer comments", key=f"comments_{document['document_id']}")
                override_reason = ""
                if action == "Approve with Override":
                    st.warning(
                        "Override means a human reviewer accepts responsibility for approving a document "
                        "that still has failed validation or unresolved warnings."
                    )
                    override_reason = st.text_input("Override reason", key=f"override_reason_{document['document_id']}")

                if st.button("Submit Reviewer Action", key=f"submit_action_{document['document_id']}"):
                    success, message = apply_reviewer_action(
                        document,
                        action,
                        reviewer_name=reviewer_name,
                        override_reason=override_reason,
                        comments=comments,
                    )
                    document["export_status"] = "Ready" if is_exportable(document) else "Blocked"
                    if success:
                        training_count = capture_approval_training(document, action, reviewer_name=reviewer_name)
                        persist_document_session()
                        readiness = "ready for export" if document["export_status"] == "Ready" else "not ready for export"
                        details = (
                            f"Review status: {document.get('review_status')}. "
                            f"Export status: {document.get('export_status')}. "
                            f"Self-training examples captured: {training_count}."
                        )
                        set_pending_notice(
                            f"{message} Document is {readiness}.",
                            details=details,
                        )
                        st.rerun()
                    else:
                        persist_document_session()
                        st.error(message)

    with export_tab:
        st.subheader("Export Approved Records")
        exportable_documents = [document for document in documents if is_exportable(document)]
        warning_documents = [document for document in documents if document.get("validation_status") == "Warning"]
        last_export = st.session_state.exports[-1]["timestamp"] if st.session_state.exports else "No export yet"
        export_summary_cols = st.columns(4)
        export_summary_cols[0].metric("Ready Documents", len(exportable_documents))
        export_summary_cols[1].metric("Validation Warnings", len(warning_documents))
        export_summary_cols[2].metric("Last Export", last_export)
        export_summary_cols[3].metric("Formats", "CSV, Excel, JSON")
        if not exportable_documents:
            st.info("No approved records are ready to export yet.")
        else:
            st.success(f"{len(exportable_documents)} document(s) are ready for export.")
            st.dataframe(enhanced_document_queue_dataframe(exportable_documents), use_container_width=True, hide_index=True)
            export_ids = [document["document_id"] for document in exportable_documents]
            download_cols = st.columns(3)
            with download_cols[0]:
                st.download_button(
                    "Download CSV",
                    data=export_to_csv(exportable_documents),
                    file_name="taxextract_ai_export.csv",
                    mime="text/csv",
                    use_container_width=True,
                    on_click=mark_exported,
                    args=(export_ids,),
                )
            with download_cols[1]:
                st.download_button(
                    "Download Excel",
                    data=export_to_excel(exportable_documents),
                    file_name="taxextract_ai_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    on_click=mark_exported,
                    args=(export_ids,),
                )
            with download_cols[2]:
                st.download_button(
                    "Download JSON",
                    data=export_to_json(exportable_documents),
                    file_name="taxextract_ai_export.json",
                    mime="application/json",
                    use_container_width=True,
                    on_click=mark_exported,
                    args=(export_ids,),
                )

            with st.expander("Excel workbook contents"):
                st.write(
                    "The Excel export includes Master_Output, Invoice, Assessment, Tax_Bill, "
                    "Validation_Log, and Audit_Log sheets."
                )

    with audit_tab:
        st.subheader("Audit Trail")
        events = collect_audit_events()
        if not events:
            st.info("No audit events yet.")
        else:
            audit_df = pd.DataFrame(events)
            if "details" in audit_df.columns:
                audit_df["details"] = audit_df["details"].astype(str)
            st.dataframe(audit_df, use_container_width=True, hide_index=True)


def main() -> None:
    inject_css()
    init_state()
    sync_section_from_query()
    st.session_state.review_queue = [
        document.get("document_id")
        for document in build_review_queue(st.session_state.processed_documents)
    ]
    app_header()
    show_pending_notice()

    render_sidebar()
    section = st.session_state.get("active_section", "Dashboard")

    if section == "Dashboard":
        dashboard_section()
    elif section == "Documents":
        documents_section()
    elif section == "Insights":
        insights_section()
    elif section == "Review & Export":
        review_export_section()


if __name__ == "__main__":
    try:
        main()
    except Exception as app_error:
        st.error("TaxExtract AI ran into an unexpected local processing issue.")
        st.info("Please refresh the app or remove the last uploaded file and try again.")
        st.caption(str(app_error))
