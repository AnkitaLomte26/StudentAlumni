"""Small private proof store. No original filenames or public static routes."""
from datetime import datetime, timezone
from io import BytesIO
import logging
from pathlib import Path
import re
import warnings
from uuid import uuid4
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from app.config import settings

MAX_PROOF_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000


def proof_path(filename):
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|pdf)", filename or ""):
        raise HTTPException(404, "Proof not found.")
    directory = Path(settings.VERIFICATION_STORAGE_DIR).resolve()
    frontend = Path(__file__).resolve().parents[3] / "frontend"
    if directory == frontend or frontend in directory.parents:
        raise RuntimeError("Verification storage cannot be inside frontend.")
    return directory / filename


def delete_proof(filename):
    if filename:
        try:
            proof_path(filename).unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning("A retired proof could not be deleted; retry local cleanup.")


def validate_proof(data, media_type):
    if not data:
        raise HTTPException(422, "Select a non-empty college ID proof.")
    if len(data) > MAX_PROOF_BYTES:
        raise HTTPException(413, "College ID proof must be at most 5 MB.")
    if media_type not in ("image/png", "image/jpeg", "application/pdf"):
        raise HTTPException(415, "Use a PNG, JPEG, or PDF file.")
    try:
        if media_type == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise ValueError()
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
                raise ValueError()
            root = reader.trailer["/Root"]
            names = root.get("/Names", {})
            if hasattr(names, "get_object"):
                names = names.get_object()
            if "/OpenAction" in root or "/AA" in root or "/JavaScript" in names or "/EmbeddedFiles" in names:
                raise ValueError()
            return "pdf"
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as img:
                expected = "PNG" if media_type == "image/png" else "JPEG"
                if img.format != expected:
                    raise ValueError()
                img.verify()
        return "png" if media_type == "image/png" else "jpg"
    except Exception as error:
        raise HTTPException(422, "File is not a valid supported image or PDF (PDFs: unencrypted, up to 20 pages, no embedded files/scripts).") from error


def save_proof(data, extension):
    filename = uuid4().hex + "." + extension
    path = proof_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(data)
    return filename


def verification_info(profile, record):
    return {
        "verification_status": profile.verification_status,
        "has_proof": bool(record and record.proof_filename),
        "submitted_at": record.submitted_at if record else None,
        "reviewed_at": record.reviewed_at if record else None,
        "rejection_reason": record.rejection_reason if record else None,
    }


def now():
    return datetime.now(timezone.utc)
