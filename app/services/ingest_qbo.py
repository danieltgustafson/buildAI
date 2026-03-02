from __future__ import annotations

"""QuickBooks Online transaction CSV ingestion service."""

import hashlib
import io
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.models.exception import Exception as ExceptionModel
from app.models.exception import ExceptionSeverity, ExceptionType
from app.models.gl_transaction import GLTransaction, TransactionCategory
from app.models.job_mapping import JobMapping
from app.schemas.ingest import IngestResult


EXPECTED_COLUMNS = {
    "date": ["date", "txn_date", "transaction_date"],
    "vendor": ["vendor", "name", "payee"],
    "amount": ["amount", "total", "debit", "net_amount"],
    "category": ["category", "account", "type", "expense_category"],
    "job_ref": ["customer", "customer:job", "class", "location", "job"],
    "memo": ["memo", "description", "notes"],
}

CATEGORY_MAP = {
    "materials": TransactionCategory.materials,
    "material": TransactionCategory.materials,
    "supplies": TransactionCategory.materials,
    "subcontractor": TransactionCategory.sub,
    "sub": TransactionCategory.sub,
    "subcontract": TransactionCategory.sub,
    "equipment": TransactionCategory.equipment,
    "rental": TransactionCategory.equipment,
    "permit": TransactionCategory.permit,
    "permits": TransactionCategory.permit,
}


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        matches = [col for col in df.columns if col.strip().lower() == c.lower()]
        if matches:
            return matches[0]
    return None


def _classify_category(raw: str | None) -> TransactionCategory:
    if raw is None:
        return TransactionCategory.other
    lower = raw.strip().lower()
    for key, cat in CATEGORY_MAP.items():
        if key in lower:
            return cat
    return TransactionCategory.other


def ingest_qbo_csv(db: Session, file_content: bytes, filename: str) -> IngestResult:
    """Parse a QBO transaction export CSV and load into gl_transactions."""
    file_hash = hashlib.sha256(file_content).hexdigest()[:16]

    df = pd.read_csv(io.BytesIO(file_content))
    df.columns = df.columns.str.strip()

    col_map = {}
    for key, candidates in EXPECTED_COLUMNS.items():
        col_map[key] = _resolve_column(df, candidates)

    if col_map["amount"] is None:
        return IngestResult(
            source="qbo",
            rows_ingested=0,
            rows_mapped=0,
            rows_unmapped=0,
            exceptions_created=0,
            message="Could not find amount column in CSV",
        )

    rows_ingested = 0
    rows_mapped = 0
    rows_unmapped = 0
    exceptions_created = 0

    for _, row in df.iterrows():
        txn_date_raw = row[col_map["date"]] if col_map["date"] else None
        try:
            txn_date = pd.to_datetime(txn_date_raw).date()
        except Exception:
            txn_date = date.today()

        vendor = str(row[col_map["vendor"]]).strip() if col_map["vendor"] and pd.notna(row.get(col_map["vendor"])) else None
        amount = float(row[col_map["amount"]]) if pd.notna(row[col_map["amount"]]) else 0

        cat_raw = str(row[col_map["category"]]) if col_map["category"] and pd.notna(row.get(col_map["category"])) else None
        category = _classify_category(cat_raw)

        memo = str(row[col_map["memo"]]).strip() if col_map["memo"] and pd.notna(row.get(col_map["memo"])) else None

        # Job mapping
        job_ref = str(row[col_map["job_ref"]]).strip() if col_map["job_ref"] and pd.notna(row.get(col_map["job_ref"])) else None
        job_id = None
        if job_ref:
            mapping = (
                db.query(JobMapping)
                .filter(JobMapping.source_system == "qbo", JobMapping.source_key == job_ref)
                .first()
            )
            if mapping and mapping.job_id:
                job_id = mapping.job_id
                rows_mapped += 1
            else:
                rows_unmapped += 1
                existing_exc = (
                    db.query(ExceptionModel)
                    .filter(
                        ExceptionModel.type == ExceptionType.UNMAPPED_TRANSACTION,
                        ExceptionModel.source_ref == f"qbo:{job_ref}",
                        ExceptionModel.resolved_at.is_(None),
                    )
                    .first()
                )
                if not existing_exc:
                    db.add(
                        ExceptionModel(
                            type=ExceptionType.UNMAPPED_TRANSACTION,
                            severity=ExceptionSeverity.warn,
                            message=f"QBO transaction has unmapped job ref: {job_ref}",
                            source_ref=f"qbo:{job_ref}",
                        )
                    )
                    exceptions_created += 1
        else:
            rows_unmapped += 1

        raw_source_id = f"qbo:{file_hash}:{rows_ingested}"
        txn = GLTransaction(
            job_id=job_id,
            txn_date=txn_date,
            vendor=vendor,
            category=category,
            amount=amount,
            raw_source_id=raw_source_id,
            description=memo,
        )
        db.add(txn)
        rows_ingested += 1

    db.commit()

    return IngestResult(
        source="qbo",
        rows_ingested=rows_ingested,
        rows_mapped=rows_mapped,
        rows_unmapped=rows_unmapped,
        exceptions_created=exceptions_created,
        message=f"Ingested {rows_ingested} QBO transactions from {filename}",
    )
