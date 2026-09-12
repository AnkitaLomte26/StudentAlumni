from math import ceil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import AccountStatus, AlumniProfile, User, UserRole, VerificationStatus
from app.models.professional import WorkExperience, Skill, UserSkill, GuidanceArea, AlumniGuidanceArea
from app.schemas.professional import AlumniPublic, SearchPage
from app.utils.deps import require_student

router = APIRouter(prefix="/api/alumni", tags=["student discovery"], dependencies=[Depends(require_student)])


def visible_query():
    return select(AlumniProfile, User.name).join(User, User.id == AlumniProfile.user_id).where(
        AlumniProfile.verification_status == VerificationStatus.VERIFIED,
        User.role == UserRole.ALUMNI, User.account_status == AccountStatus.ACTIVE)


def public_profiles(db, rows, company_id=None):
    ids = [profile.user_id for profile, name in rows]
    if not ids:
        return []
    works = {uid: [] for uid in ids}
    skills = {uid: [] for uid in ids}
    areas = {uid: [] for uid in ids}
    for item in db.scalars(select(WorkExperience).options(joinedload(WorkExperience.company))
                           .where(WorkExperience.alumni_user_id.in_(ids))
                           .order_by(WorkExperience.end_date.is_not(None), WorkExperience.start_date.desc(), WorkExperience.id)):
        works[item.alumni_user_id].append(item)
    for uid, item in db.execute(select(UserSkill.user_id, Skill).join(Skill).where(UserSkill.user_id.in_(ids)).order_by(Skill.name)):
        skills[uid].append(item)
    for uid, item in db.execute(select(AlumniGuidanceArea.alumni_user_id, GuidanceArea).join(GuidanceArea)
                               .where(AlumniGuidanceArea.alumni_user_id.in_(ids)).order_by(GuidanceArea.name)):
        areas[uid].append(item)
    result = []
    for profile, name in rows:
        uid = profile.user_id
        matching = [w for w in works[uid] if w.company_id == company_id]
        result.append({
            "user_id": uid, "name": name, "branch": profile.branch,
            "graduation_year": profile.graduation_year, "bio": profile.bio,
            "verification_status": profile.verification_status,
            "accepting_guidance_requests": profile.accepting_guidance_requests,
            "company_relation": ("CURRENT" if any(w.end_date is None for w in matching) else "PREVIOUS") if matching else None,
            "work_experiences": works[uid], "skills": skills[uid], "guidance_areas": areas[uid],
        })
    return result


@router.get("", response_model=SearchPage)
def search(company_id: int | None = Query(None, gt=0),
           role: str = Query("", max_length=120), domain: str = Query("", max_length=120),
           branch: str = Query("", max_length=120), graduation_year: int | None = Query(None, ge=1950, le=2100),
           graduation_year_from: int | None = Query(None, ge=1950, le=2100),
           graduation_year_to: int | None = Query(None, ge=1950, le=2100),
           skill_ids: list[int] = Query([], max_length=20),
           guidance_area_ids: list[int] = Query([], max_length=20),
           accepting_guidance_requests: bool | None = None,
           page: int = Query(1, ge=1, le=100000), page_size: int = Query(12, ge=1, le=50),
           db: Session = Depends(get_db)):
    if graduation_year_from and graduation_year_to and graduation_year_from > graduation_year_to:
        raise HTTPException(422, "Graduation year range is reversed.")
    if any(i <= 0 for i in skill_ids + guidance_area_ids):
        raise HTTPException(422, "Filter IDs must be positive.")
    query = visible_query()
    work_filters = [WorkExperience.alumni_user_id == AlumniProfile.user_id]
    if company_id:
        work_filters.append(WorkExperience.company_id == company_id)
    if role.strip():
        work_filters.append(WorkExperience.role.icontains(role.strip(), autoescape=True))
    if domain.strip():
        work_filters.append(WorkExperience.domain.icontains(domain.strip(), autoescape=True))
    # Company, role and domain must match the SAME job, avoiding unrelated-history matches.
    if len(work_filters) > 1:
        query = query.where(exists(select(WorkExperience.id).where(*work_filters)))
    if branch.strip():
        query = query.where(AlumniProfile.branch.icontains(branch.strip(), autoescape=True))
    if graduation_year:
        query = query.where(AlumniProfile.graduation_year == graduation_year)
    if graduation_year_from:
        query = query.where(AlumniProfile.graduation_year >= graduation_year_from)
    if graduation_year_to:
        query = query.where(AlumniProfile.graduation_year <= graduation_year_to)
    if accepting_guidance_requests is not None:
        query = query.where(AlumniProfile.accepting_guidance_requests == accepting_guidance_requests)
    # Each selected skill/area is required (AND semantics); EXISTS avoids duplicate rows.
    for sid in set(skill_ids):
        query = query.where(exists(select(UserSkill.user_id).where(
            UserSkill.user_id == AlumniProfile.user_id, UserSkill.skill_id == sid)))
    for aid in set(guidance_area_ids):
        query = query.where(exists(select(AlumniGuidanceArea.alumni_user_id).where(
            AlumniGuidanceArea.alumni_user_id == AlumniProfile.user_id, AlumniGuidanceArea.guidance_area_id == aid)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    if company_id:
        current = exists(select(WorkExperience.id).where(
            WorkExperience.alumni_user_id == AlumniProfile.user_id,
            WorkExperience.company_id == company_id, WorkExperience.end_date.is_(None)))
        query = query.order_by(case((current, 0), else_=1))
    query = query.order_by(func.lower(User.name), AlumniProfile.user_id)
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": public_profiles(db, rows, company_id), "page": page, "page_size": page_size,
            "total_results": total, "total_pages": ceil(total / page_size)}


@router.get("/{user_id}", response_model=AlumniPublic)
def profile(user_id: int, db: Session = Depends(get_db)):
    rows = db.execute(visible_query().where(AlumniProfile.user_id == user_id)).all()
    if not rows:
        raise HTTPException(404, "Verified alumni profile not found.")
    return public_profiles(db, rows)[0]
