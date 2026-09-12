from math import ceil
import logging
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AlumniProfile, User, VerificationStatus
from app.models.professional import AlumniVerification
from app.schemas.professional import AdminVerification, ReviewInput, VerificationPublic
from app.services.verification import MAX_PROOF_BYTES, delete_proof, now, proof_path, save_proof, validate_proof, verification_info
from app.routes.professional import trusted_origin
from app.utils.deps import require_admin, require_alumni

router = APIRouter(prefix="/api", tags=["college identity verification"], dependencies=[Depends(trusted_origin)])


def locked_profile(db, user_id):
    profile = db.scalar(select(AlumniProfile).where(AlumniProfile.user_id == user_id).with_for_update())
    if not profile:
        raise HTTPException(404, "Alumni profile not found.")
    return profile


@router.get("/profiles/alumni/me/verification", response_model=VerificationPublic)
def own_status(db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    return verification_info(db.get(AlumniProfile, user.id), db.get(AlumniVerification, user.id))


@router.post("/profiles/alumni/me/verification", response_model=VerificationPublic, status_code=201)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    try:
        data = file.file.read(MAX_PROOF_BYTES + 1)
        extension = validate_proof(data, file.content_type)
    finally:
        file.file.close()
    profile = locked_profile(db, user.id)
    if profile.verification_status == VerificationStatus.VERIFIED:
        raise HTTPException(409, "Your college-alumni identity is already verified.")
    record = db.get(AlumniVerification, user.id)
    old_filename = record.proof_filename if record else None
    filename = save_proof(data, extension)
    try:
        if not record:
            record = AlumniVerification(alumni_user_id=user.id)
            db.add(record)
        record.proof_filename = filename
        record.proof_media_type = file.content_type
        record.submitted_at = now()
        record.reviewed_at = None
        record.reviewed_by = None
        record.rejection_reason = None
        profile.verification_status = VerificationStatus.PENDING
        db.commit()
    except Exception:
        db.rollback()
        delete_proof(filename)
        raise
    delete_proof(old_filename)
    return verification_info(profile, record)


def admin_info(profile, record, user):
    return {**verification_info(profile, record), "user_id": user.id, "name": user.name,
            "email": user.email, "branch": profile.branch, "graduation_year": profile.graduation_year,
            "proof_media_type": record.proof_media_type if record else None}


@router.get("/admin/verifications")
def pending(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
            db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    query = select(AlumniProfile, AlumniVerification, User).join(
        AlumniVerification, AlumniVerification.alumni_user_id == AlumniProfile.user_id).join(
        User, User.id == AlumniProfile.user_id).where(
        AlumniProfile.verification_status == VerificationStatus.PENDING,
        AlumniVerification.proof_filename.is_not(None))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(AlumniVerification.submitted_at, User.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [AdminVerification(**admin_info(p, r, u)) for p, r, u in rows],
            "page": page, "page_size": page_size, "total_results": total, "total_pages": ceil(total / page_size)}


@router.get("/admin/verifications/{user_id}", response_model=AdminVerification)
def info(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    profile = db.get(AlumniProfile, user_id)
    if not profile:
        raise HTTPException(404, "Alumni profile not found.")
    return admin_info(profile, db.get(AlumniVerification, user_id), db.get(User, user_id))


@router.get("/admin/verifications/{user_id}/proof")
def proof(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    record = db.get(AlumniVerification, user_id)
    if not record or not record.proof_filename:
        raise HTTPException(404, "Proof file is unavailable. Ask the alumni to upload it again.")
    path = proof_path(record.proof_filename)
    if not path.is_file():
        raise HTTPException(404, "Proof file is unavailable. Ask the alumni to upload it again.")
    if record.proof_media_type not in ("image/png", "image/jpeg", "application/pdf"):
        raise HTTPException(404, "Proof file is unavailable. Ask the alumni to upload it again.")
    return FileResponse(path, media_type=record.proof_media_type,
                        headers={"Content-Disposition": "inline", "Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "sandbox; default-src 'none'"})


@router.post("/admin/verifications/{user_id}/review", response_model=AdminVerification)
def review(user_id: int, payload: ReviewInput, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    profile = locked_profile(db, user_id)
    record = db.get(AlumniVerification, user_id)
    if profile.verification_status != VerificationStatus.PENDING or not record or not record.proof_filename:
        raise HTTPException(409, "A pending request with college ID proof is required.")
    if not proof_path(record.proof_filename).is_file():
        raise HTTPException(409, "Proof is unavailable; request a fresh upload before reviewing.")
    retired = record.proof_filename
    profile.verification_status = VerificationStatus(payload.decision)
    record.reviewed_at = now()
    record.reviewed_by = admin.id
    record.rejection_reason = payload.reason.strip() if payload.decision == "REJECTED" else None
    record.proof_filename = None
    record.proof_media_type = None
    db.commit()
    # Retain decision metadata, remove sensitive proof after either decision.
    logging.getLogger("platform.audit").info("verification_review admin_id=%s alumni_id=%s decision=%s", admin.id, user_id, payload.decision)
    delete_proof(retired)
    return admin_info(profile, record, db.get(User, user_id))
