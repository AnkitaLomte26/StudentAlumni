from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.models.professional import Company, Skill, GuidanceArea, WorkExperience, UserSkill, AlumniGuidanceArea
from app.schemas.professional import CatalogCreate, NamedItem, WorkInput, WorkPublic
from app.services.catalogs import CATALOGS
from app.utils.deps import get_current_user, require_admin, require_alumni


def trusted_origin(request: Request):
    # JSON endpoints and multipart uploads retain cookie sessions; reject cross-origin writes.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            raise HTTPException(403, "Untrusted request origin.")
        if not origin and request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Untrusted request origin.")


router = APIRouter(prefix="/api", tags=["professional"], dependencies=[Depends(trusted_origin)])


def member(user: User = Depends(get_current_user)):
    if user.role not in (UserRole.STUDENT, UserRole.ALUMNI):
        raise HTTPException(403, "Student or alumni account required.")
    return user


def commit_unique(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This item is already added or its reference is invalid.") from None


@router.get("/catalogs/{catalog}", response_model=list[NamedItem])
def catalog_list(catalog: str, q: str = Query("", max_length=120),
                 limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    model = CATALOGS.get(catalog)
    if not model:
        raise HTTPException(404, "Catalog not found.")
    return db.scalars(select(model).where(model.name.icontains(q.strip(), autoescape=True))
                      .order_by(func.lower(model.name), model.id).offset(offset).limit(limit)).all()


@router.post("/catalogs/{catalog}", response_model=NamedItem, status_code=201)
def catalog_add(catalog: str, payload: CatalogCreate, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    model = CATALOGS.get(catalog)
    if not model:
        raise HTTPException(404, "Catalog not found.")
    if db.scalar(select(model.id).where(func.lower(model.name) == payload.name.lower())):
        raise HTTPException(409, "An entry with this name already exists in this catalog.")
    item = model(name=payload.name)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An entry with this name already exists in this catalog.") from None
    return item


@router.get("/profiles/alumni/me/work-experiences", response_model=list[WorkPublic])
def work_list(db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    return db.scalars(select(WorkExperience).options(joinedload(WorkExperience.company))
                      .where(WorkExperience.alumni_user_id == user.id)
                      .order_by(WorkExperience.start_date.desc(), WorkExperience.id.desc())).all()


def owned_work(db, user, work_id):
    item = db.scalar(select(WorkExperience).where(WorkExperience.id == work_id,
                                                WorkExperience.alumni_user_id == user.id))
    if not item:
        raise HTTPException(404, "Work experience not found.")
    return item


def check_company(db, company_id):
    if not db.get(Company, company_id):
        raise HTTPException(422, "Select an existing company.")


@router.post("/profiles/alumni/me/work-experiences", response_model=WorkPublic, status_code=201)
def work_add(payload: WorkInput, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    check_company(db, payload.company_id)
    item = WorkExperience(alumni_user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    return item


@router.put("/profiles/alumni/me/work-experiences/{work_id}", response_model=WorkPublic)
def work_update(work_id: int, payload: WorkInput, db: Session = Depends(get_db),
                user: User = Depends(require_alumni)):
    item = owned_work(db, user, work_id)
    check_company(db, payload.company_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/profiles/alumni/me/work-experiences/{work_id}", status_code=204)
def work_delete(work_id: int, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    db.delete(owned_work(db, user, work_id))
    db.commit()


@router.get("/profiles/me/skills", response_model=list[NamedItem])
def skills_list(db: Session = Depends(get_db), user: User = Depends(member)):
    return db.scalars(select(Skill).join(UserSkill).where(UserSkill.user_id == user.id)
                      .order_by(Skill.name)).all()


@router.post("/profiles/me/skills/{skill_id}", status_code=201, response_model=NamedItem)
def skill_add(skill_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    item = db.get(Skill, skill_id)
    if not item:
        raise HTTPException(404, "Skill not found.")
    if db.get(UserSkill, (user.id, skill_id)):
        raise HTTPException(409, "Skill already added.")
    db.add(UserSkill(user_id=user.id, skill_id=skill_id))
    commit_unique(db)
    return item


@router.delete("/profiles/me/skills/{skill_id}", status_code=204)
def skill_delete(skill_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    item = db.get(UserSkill, (user.id, skill_id))
    if not item:
        raise HTTPException(404, "Skill relationship not found.")
    db.delete(item)
    db.commit()


@router.get("/profiles/alumni/me/guidance-areas", response_model=list[NamedItem])
def guidance_list(db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    return db.scalars(select(GuidanceArea).join(AlumniGuidanceArea)
                      .where(AlumniGuidanceArea.alumni_user_id == user.id)
                      .order_by(GuidanceArea.name)).all()


@router.post("/profiles/alumni/me/guidance-areas/{area_id}", status_code=201, response_model=NamedItem)
def guidance_add(area_id: int, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    item = db.get(GuidanceArea, area_id)
    if not item:
        raise HTTPException(404, "Guidance area not found.")
    if db.get(AlumniGuidanceArea, (user.id, area_id)):
        raise HTTPException(409, "Guidance area already added.")
    db.add(AlumniGuidanceArea(alumni_user_id=user.id, guidance_area_id=area_id))
    commit_unique(db)
    return item


@router.delete("/profiles/alumni/me/guidance-areas/{area_id}", status_code=204)
def guidance_delete(area_id: int, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    item = db.get(AlumniGuidanceArea, (user.id, area_id))
    if not item:
        raise HTTPException(404, "Guidance area relationship not found.")
    db.delete(item)
    db.commit()
