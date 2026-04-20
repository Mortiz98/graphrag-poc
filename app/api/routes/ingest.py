import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.exceptions import UnsupportedFileTypeError
from app.models.schemas import CaseMetadata, FactMetadata, IngestResponse
from app.pipelines.ingestion import ingest_document

router = APIRouter(prefix="/api/v1", tags=["ingest"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}

SAMPLE_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "test_data"


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Upload and process a document",
    description="Upload a PDF, TXT, or Markdown file. The document will be chunked, "
    "triplets extracted via LLM, and stored in both NebulaGraph and Qdrant. "
    "Supports system routing ('support' or 'am') and domain-specific metadata.",
    responses={
        200: {"description": "Document processed successfully"},
        400: {"description": "Unsupported file type"},
        503: {"description": "Backend service unavailable"},
    },
)
async def ingest_file(
    file: UploadFile = File(...),
    system: str = Form("support"),
    tenant_id: str | None = Form(None),
    user_id: str | None = Form(None),
    case_id: str | None = Form(None),
    product: str | None = Form(None),
    version: str | None = Form(None),
    severity: str | None = Form(None),
    channel: str | None = Form(None),
    team: str | None = Form(None),
    status: str | None = Form(None),
    account_id: str | None = Form(None),
    fact_type: str | None = Form(None),
    valid_from: str | None = Form(None),
    valid_to: str | None = Form(None),
    supersedes: str | None = Form(None),
    stakeholder: str | None = Form(None),
    confidence: float | None = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(suffix)

    case_metadata = None
    if any([tenant_id, case_id, product, version, severity, channel, team, status]):
        case_metadata = CaseMetadata(
            tenant_id=tenant_id,
            case_id=case_id,
            product=product,
            version=version,
            severity=severity,
            channel=channel,
            team=team,
            status=status,
        )

    fact_metadata = None
    if any([tenant_id, account_id, user_id, fact_type, valid_from, valid_to, supersedes, stakeholder, confidence]):
        fact_metadata = FactMetadata(
            tenant_id=tenant_id,
            account_id=account_id,
            user_id=user_id,
            fact_type=fact_type,
            valid_from=valid_from,
            valid_to=valid_to,
            supersedes=supersedes,
            stakeholder=stakeholder,
            confidence=confidence,
        )

    tmp_dir = tempfile.mkdtemp()
    safe_name = Path(file.filename).name
    tmp_path = Path(tmp_dir) / safe_name
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = ingest_document(
            tmp_path,
            system=system,
            case_metadata=case_metadata,
            fact_metadata=fact_metadata,
        )

        return IngestResponse(
            filename=result["filename"],
            chunks_count=result["chunks_count"],
            triplets_count=result["triplets_count"],
            status=result["status"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Error processing document: {str(e)}",
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        Path(tmp_dir).rmdir()


@router.post(
    "/seed",
    response_model=IngestResponse,
    summary="Ingest sample data",
    description="Ingest the sample.txt file from test_data directory.",
    responses={
        200: {"description": "Sample data processed successfully"},
        404: {"description": "Sample file not found"},
        503: {"description": "Backend service unavailable"},
    },
)
async def seed_data():
    sample_file = SAMPLE_DATA_DIR / "sample.txt"
    if not sample_file.exists():
        raise HTTPException(status_code=404, detail="Sample file not found")

    try:
        result = ingest_document(sample_file)
        return IngestResponse(
            filename=result["filename"],
            chunks_count=result["chunks_count"],
            triplets_count=result["triplets_count"],
            status=result["status"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Error processing sample data: {str(e)}",
        )
