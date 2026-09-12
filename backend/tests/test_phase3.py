from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image
from sqlalchemy import select
from app.config import settings
from app.database import SessionLocal
from app.models import User, UserRole, AccountStatus
from app.models.professional import Company, Skill, GuidanceArea, AlumniVerification
from app.services.catalogs import seed_catalogs
from app.utils.security import hash_password
from tests.conftest import ALUMNI, STUDENT


def png():
    data = BytesIO()
    Image.new("RGB", (32, 32), "white").save(data, format="PNG")
    return data.getvalue()


def jpeg():
    data = BytesIO()
    Image.new("RGB", (32, 32), "white").save(data, format="JPEG")
    return data.getvalue()


def pdf():
    from pypdf import PdfWriter
    data = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(data)
    return data.getvalue()


def login(client, person):
    assert client.post("/api/auth/login", json={"email": person["email"], "password": person["password"]}).status_code == 200


def register(client, person):
    response = client.post("/api/auth/register", json=person)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def world(client):
    admin = {"email": "admin@example.com", "password": "AdminTest123"}
    with SessionLocal() as db:
        seed_catalogs(db)
        db.add(User(name="Test Admin", email=admin["email"], password_hash=hash_password(admin["password"]),
                    role=UserRole.ADMIN, account_status=AccountStatus.ACTIVE))
        db.commit()
        companies = {x.name: x.id for x in db.scalars(select(Company))}
        skills = {x.name: x.id for x in db.scalars(select(Skill))}
        areas = {x.name: x.id for x in db.scalars(select(GuidanceArea))}
    student_id = register(client, STUDENT)
    alumni_id = register(client, ALUMNI)
    login(client, ALUMNI)
    return {"admin": admin, "companies": companies, "skills": skills, "areas": areas,
            "student_id": student_id, "alumni_id": alumni_id}


def job(world, company="Microsoft", **changes):
    return {"company_id": world["companies"][company], "role": "Software Engineer",
            "domain": "Backend", "start_date": "2020-01-01", "end_date": None, **changes}


WORK = "/api/profiles/alumni/me/work-experiences"
VERIFY = "/api/profiles/alumni/me/verification"


def approve(client, world, person=ALUMNI, user_id=None):
    login(client, person)
    assert client.post(VERIFY, files={"file": ("../../proof.png", png(), "image/png")}).status_code == 201
    login(client, world["admin"])
    user_id = user_id or world["alumni_id"]
    response = client.post(f"/api/admin/verifications/{user_id}/review", json={"decision": "VERIFIED"})
    assert response.status_code == 200, response.text


def test_student_cannot_create_work(client, world):
    login(client, STUDENT)
    assert client.post(WORK, json=job(world)).status_code == 403


def test_alumni_multiple_work_and_update_delete(client, world):
    a = client.post(WORK, json=job(world))
    b = client.post(WORK, json=job(world, "Amazon"))
    assert a.status_code == b.status_code == 201
    assert len(client.get(WORK).json()) == 2
    wid = a.json()["id"]
    assert client.put(f"{WORK}/{wid}", json=job(world, role="Senior Engineer")).json()["role"] == "Senior Engineer"
    assert client.delete(f"{WORK}/{wid}").status_code == 204
    assert len(client.get(WORK).json()) == 1


@pytest.mark.parametrize("change", [
    {"end_date": "2019-12-01"}, {"start_date": "2100-01-01"},
    {"end_date": "not-a-date"}, {"company_id": 999999},
    {"role": " "}, {"domain": "x" * 121},
])
def test_invalid_work_rejected(client, world, change):
    assert client.post(WORK, json=job(world, **change)).status_code == 422


def test_work_ownership(client, world):
    wid = client.post(WORK, json=job(world)).json()["id"]
    other = {**ALUMNI, "email": "other@example.com"}
    register(client, other)
    login(client, other)
    assert client.get(WORK).json() == []
    assert client.put(f"{WORK}/{wid}", json=job(world)).status_code == 404
    assert client.delete(f"{WORK}/{wid}").status_code == 404


@pytest.mark.parametrize("person", [STUDENT, ALUMNI])
def test_skills_for_both_roles_and_duplicates(client, world, person):
    login(client, person)
    sid = world["skills"]["Python"]
    url = f"/api/profiles/me/skills/{sid}"
    assert client.post(url).status_code == 201
    assert client.post(url).status_code == 409
    assert client.get("/api/profiles/me/skills").json() == [{"id": sid, "name": "Python"}]
    assert client.delete(url).status_code == 204
    assert client.get("/api/profiles/me/skills").json() == []


def test_guidance_multiple_duplicates_and_student_denied(client, world):
    url = "/api/profiles/alumni/me/guidance-areas"
    for aid in list(world["areas"].values())[:2]:
        assert client.post(f"{url}/{aid}").status_code == 201
    assert len(client.get(url).json()) == 2
    assert client.post(f"{url}/{aid}").status_code == 409
    assert client.delete(f"{url}/{aid}").status_code == 204
    login(client, STUDENT)
    assert client.post(f"{url}/{aid}").status_code == 403


def test_unverified_hidden_and_profile_private(client, world):
    login(client, STUDENT)
    assert client.get("/api/alumni").json()["total_results"] == 0
    assert client.get(f"/api/alumni/{world['alumni_id']}").status_code == 404


def test_approved_visible_and_no_private_fields(client, world):
    approve(client, world)
    login(client, STUDENT)
    data = client.get("/api/alumni").json()
    assert data["total_results"] == 1
    profile = client.get(f"/api/alumni/{world['alumni_id']}").json()
    assert profile["verification_status"] == "VERIFIED"
    for private in ["email", "password_hash", "proof_filename", "reviewed_by", "account_status"]:
        assert private not in profile


def test_company_current_before_previous_and_no_duplicate_results(client, world):
    # Alphabetical order would put previous first; current-company priority overrides it.
    client.post(WORK, json=job(world, end_date="2022-01-01"))
    approve(client, world)
    other = {**ALUMNI, "name": "Zed Current", "email": "current@example.com"}
    uid = register(client, other)
    login(client, other)
    client.post(WORK, json=job(world))
    client.post(WORK, json=job(world, role="Team Lead"))
    approve(client, world, other, uid)
    login(client, STUDENT)
    response = client.get("/api/alumni", params={"company_id": world["companies"]["Microsoft"]})
    data = response.json()
    assert data["total_results"] == 2
    assert [x["company_relation"] for x in data["items"]] == ["CURRENT", "PREVIOUS"]
    assert data["items"][0]["name"] == "Zed Current"
    assert client.get("/api/alumni", params={"company_id": world["companies"]["Google"]}).json()["items"] == []


def test_skills_and_combined_filters(client, world):
    client.post(WORK, json=job(world))
    sid = world["skills"]["Python"]
    aid = world["areas"]["Interview Preparation"]
    client.post(f"/api/profiles/me/skills/{sid}")
    client.post(f"/api/profiles/alumni/me/guidance-areas/{aid}")
    approve(client, world)
    login(client, STUDENT)
    assert client.get("/api/alumni", params={"skill_ids": sid}).json()["total_results"] == 1
    params = {"company_id": world["companies"]["Microsoft"], "skill_ids": sid, "guidance_area_ids": aid,
              "domain": "back", "role": "engineer", "branch": "electrical", "graduation_year_from": 2017,
              "graduation_year_to": 2019, "accepting_guidance_requests": "true"}
    assert client.get("/api/alumni", params=params).json()["total_results"] == 1
    params["branch"] = "Mechanical"
    assert client.get("/api/alumni", params=params).json()["total_results"] == 0
    assert client.get("/api/alumni", params=[("skill_ids", sid), ("skill_ids", world["skills"]["SQL"])]).json()["total_results"] == 0


def test_company_and_domain_must_match_same_job(client, world):
    client.post(WORK, json=job(world, domain="Frontend"))
    client.post(WORK, json=job(world, "Amazon", domain="Backend"))
    approve(client, world)
    login(client, STUDENT)
    assert client.get("/api/alumni", params={"company_id": world["companies"]["Microsoft"], "domain": "Backend"}).json()["items"] == []


def test_pagination_stable_and_bounded(client, world):
    approve(client, world)
    other = {**ALUMNI, "email": "second@example.com"}
    uid = register(client, other)
    approve(client, world, other, uid)
    login(client, STUDENT)
    first = client.get("/api/alumni", params={"page_size": 1}).json()
    second = client.get("/api/alumni", params={"page_size": 1, "page": 2}).json()
    assert first["total_results"] == first["total_pages"] == 2
    assert first["items"][0]["user_id"] != second["items"][0]["user_id"]
    assert client.get("/api/alumni", params={"page": 3, "page_size": 1}).json()["items"] == []
    assert client.get("/api/alumni", params={"page_size": 51}).status_code == 422
    assert client.get("/api/alumni", params={"graduation_year_from": 2025, "graduation_year_to": 2020}).status_code == 422


@pytest.mark.parametrize("person", [ALUMNI, {"email": "admin@example.com", "password": "AdminTest123"}])
def test_only_students_discover(client, world, person):
    login(client, person)
    assert client.get("/api/alumni").status_code == 403
    assert client.get(f"/api/alumni/{world['alumni_id']}").status_code == 403


def test_anonymous_discovery_and_proof_denied(client, world):
    client.post("/api/auth/logout")
    assert client.get("/api/alumni").status_code == 401
    assert client.get(f"/api/admin/verifications/{world['alumni_id']}/proof").status_code == 401


@pytest.mark.parametrize("person", [ALUMNI, STUDENT])
def test_normal_users_cannot_access_proof_or_review(client, world, person):
    client.post(VERIFY, files={"file": ("proof.png", png(), "image/png")})
    login(client, person)
    url = f"/api/admin/verifications/{world['alumni_id']}"
    assert client.get(url + "/proof").status_code == 403
    assert client.post(url + "/review", json={"decision": "VERIFIED"}).status_code == 403


@pytest.mark.parametrize("decision", ["VERIFIED", "REJECTED"])
def test_admin_review_and_proof_retirement(client, world, decision):
    client.post(VERIFY, files={"file": ("../../unsafe.png", png(), "image/png")})
    with SessionLocal() as db:
        name = db.get(AlumniVerification, world["alumni_id"]).proof_filename
        assert "/" not in name and "unsafe" not in name
    login(client, world["admin"])
    url = f"/api/admin/verifications/{world['alumni_id']}"
    assert len(client.get("/api/admin/verifications").json()["items"]) == 1
    proof = client.get(url + "/proof")
    assert proof.status_code == 200 and proof.content == png()
    assert proof.headers["cache-control"] == "no-store"
    assert proof.headers["content-type"] == "image/png"
    assert proof.headers["content-disposition"] == "inline"
    assert proof.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in proof.headers["content-security-policy"]
    assert name not in str(proof.headers)
    response = client.post(url + "/review", json={"decision": decision, "reason": "College ID needs clarification."})
    assert response.status_code == 200
    assert response.json()["verification_status"] == decision
    assert response.json()["has_proof"] is False
    assert not (Path(settings.VERIFICATION_STORAGE_DIR) / name).exists()
    assert client.get(url + "/proof").status_code == 404
    assert client.post(url + "/review", json={"decision": "VERIFIED"}).status_code == 409
    login(client, STUDENT)
    assert client.get("/api/alumni").json()["total_results"] == (1 if decision == "VERIFIED" else 0)


def test_admin_cannot_approve_without_proof_and_public_admin_denied(client, world):
    login(client, world["admin"])
    assert client.post(f"/api/admin/verifications/{world['alumni_id']}/review", json={"decision": "VERIFIED"}).status_code == 409
    assert client.post("/api/auth/register", json={**ALUMNI, "email": "bad@example.com", "role": "ADMIN"}).status_code == 422


def test_rejected_alumni_can_resubmit(client, world):
    client.post(VERIFY, files={"file": ("id.png", png(), "image/png")})
    login(client, world["admin"])
    client.post(f"/api/admin/verifications/{world['alumni_id']}/review", json={"decision": "REJECTED", "reason": "Unreadable."})
    login(client, ALUMNI)
    response = client.post(VERIFY, files={"file": ("new.png", png(), "image/png")})
    assert response.status_code == 201
    assert response.json()["verification_status"] == "PENDING"
    assert response.json()["rejection_reason"] is None


@pytest.mark.parametrize("media,data", [("text/html", b"<html>"), ("image/png", b"not a png"), ("application/pdf", b"%PDF-fake")])
def test_invalid_uploads(client, world, media, data):
    assert client.post(VERIFY, files={"file": ("id.png", data, media)}).status_code in (415, 422)


def test_upload_size_and_csrf(client, world):
    assert client.post(VERIFY, files={"file": ("id.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")}).status_code == 413
    assert client.post(VERIFY, files={"file": ("id.png", png(), "image/png")}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_catalog_search_seed_repeatability_and_case_duplicates(client, world):
    assert client.get("/api/catalogs/companies", params={"q": "micro"}).json() == [{"id": world["companies"]["Microsoft"], "name": "Microsoft"}]
    with SessionLocal() as db:
        seed_catalogs(db)
        assert len(db.scalars(select(Company)).all()) == len(world["companies"])
    login(client, world["admin"])
    assert client.post("/api/catalogs/companies", json={"name": " microsoft "}).status_code == 409


@pytest.mark.parametrize("catalog,name", [("companies","Example Company"),("skills","Rust"),("guidance-areas","Technical Leadership")])
def test_catalog_admin_add_pagination_and_role_authorization(client, world, catalog, name):
    url=f"/api/catalogs/{catalog}"
    for person in (STUDENT, ALUMNI):
        login(client, person)
        assert client.post(url, json={"name":name}).status_code == 403
    login(client, world["admin"])
    added = client.post(url, json={"name":name})
    assert added.status_code == 201 and added.json()["name"] == name
    duplicate=client.post(url, json={"name":" "+name.lower()+" "})
    assert duplicate.status_code == 409 and "already exists" in duplicate.json()["detail"]
    assert client.get(url, params={"q":name.lower()}).json() == [added.json()]
    page1=client.get(url, params={"limit":2}).json()
    page2=client.get(url, params={"limit":2,"offset":2}).json()
    assert len(page2)==2 and not {x["id"] for x in page1}&{x["id"] for x in page2}
    assert client.get(url, params={"offset":-1}).status_code==422


def test_expanded_seed_preserves_ids_and_creates_no_users(client, world):
    with SessionLocal() as db:
        before={model:{x.id:x.name for x in db.scalars(select(model))} for model in (Company,Skill,GuidanceArea,User)}
        seed_catalogs(db)
        seed_catalogs(db)
        after={model:{x.id:x.name for x in db.scalars(select(model))} for model in before}
        assert before==after
        assert "Cybersecurity" in after[Skill].values()
        assert "Scholarship Applications" in after[GuidanceArea].values()


@pytest.mark.parametrize("kind", ["JPEG", "PDF"])
def test_other_supported_proofs(client, world, kind):
    if kind == "JPEG":
        data, media = jpeg(), "image/jpeg"
    else:
        data, media = pdf(), "application/pdf"
    assert client.post(VERIFY, files={"file": ("ignored-name", data, media)}).status_code == 201
    with SessionLocal() as db:
        stored_name = db.get(AlumniVerification, world["alumni_id"]).proof_filename
    login(client, world["admin"])
    response = client.get(f"/api/admin/verifications/{world['alumni_id']}/proof")
    assert response.status_code == 200 and response.content == data
    assert response.headers["content-type"] == media
    assert response.headers["content-disposition"] == "inline"
    assert response.headers["cache-control"] == "no-store"
    assert stored_name not in str(response.headers)


def test_admin_missing_proof_file_has_actionable_message(client, world):
    client.post(VERIFY, files={"file": ("proof.png", png(), "image/png")})
    with SessionLocal() as db:
        stored_name = db.get(AlumniVerification, world["alumni_id"]).proof_filename
    (Path(settings.VERIFICATION_STORAGE_DIR) / stored_name).unlink()
    login(client, world["admin"])
    response = client.get(f"/api/admin/verifications/{world['alumni_id']}/proof")
    assert response.status_code == 404
    assert response.json()["detail"] == "Proof file is unavailable. Ask the alumni to upload it again."
    assert client.get("/api/admin/verifications").json()["total_results"] == 1


def test_proof_has_no_public_route_and_verified_upload_blocked(client, world):
    client.post(VERIFY, files={"file": ("proof.png", png(), "image/png")})
    with SessionLocal() as db:
        filename = db.get(AlumniVerification, world["alumni_id"]).proof_filename
    assert client.get("/private_uploads/" + filename).status_code == 404
    approve(client, world)
    login(client, ALUMNI)
    assert client.post(VERIFY, files={"file": ("proof.png", png(), "image/png")}).status_code == 409
