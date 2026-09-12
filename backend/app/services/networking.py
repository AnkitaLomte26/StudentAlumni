"""All state changes share one transaction and lock order. No commits in helpers."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.config import settings
from app.models import AccountStatus, AlumniProfile, StudentProfile, User, UserRole, VerificationStatus
from app.models.professional import GuidanceArea, Skill, UserSkill
from app.models.networking import Connection, GuidanceRequest, Notification


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


@contextmanager
def transaction(db):
    # Auth dependencies may already have begun a SQLAlchemy transaction.
    try:
        yield
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This relationship changed or a pending request already exists. Refresh and try again.") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Could not save the change. Nothing was changed; please try again.") from None
    except Exception:
        db.rollback()
        raise


def lock_pair(db, student_id, alumni_id):
    # EVERY request/connection mutation locks the student first. A count taken
    # under this lock cannot race with another mutation of this student's quota.
    student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == student_id)
                        .with_for_update().execution_options(populate_existing=True))
    alumni = db.scalar(select(AlumniProfile).where(AlumniProfile.user_id == alumni_id)
                       .with_for_update().execution_options(populate_existing=True))
    if not student or not alumni:
        raise HTTPException(404, "Student/alumni pair not found.")
    users = db.scalars(select(User).where(User.id.in_([student_id, alumni_id])).order_by(User.id)
                       .with_for_update().execution_options(populate_existing=True)).all()
    identities = {user.id: user for user in users}
    if identities[student_id].role != UserRole.STUDENT or identities[alumni_id].role != UserRole.ALUMNI:
        raise HTTPException(404, "Student/alumni pair not found.")
    return alumni, identities


def eligible_accounts(alumni, identities):
    if any(user.account_status != AccountStatus.ACTIVE for user in identities.values()):
        raise HTTPException(409, "Both accounts must be active.")
    if alumni.verification_status != VerificationStatus.VERIFIED:
        raise HTTPException(409, "This alumni's college identity is not verified.")


def pair_connection(db, student_id, alumni_id):
    return db.scalar(select(Connection).where(Connection.student_user_id == student_id,
                                             Connection.alumni_user_id == alumni_id)
                     .with_for_update().execution_options(populate_existing=True))


def notify(db, user_id, request_id, kind):
    messages = {
        "REQUEST_RECEIVED": "You received a new guidance request.",
        "REQUEST_ACCEPTED": "Your guidance request was accepted. You are now connected.",
        "REQUEST_REJECTED": "Your guidance request was rejected. See the request for your next eligible date.",
    }
    db.add(Notification(user_id=user_id, request_id=request_id, type=kind, message=messages[kind]))


def create_request(db, user, payload):
    with transaction(db):
        alumni, identities = lock_pair(db, user.id, payload.alumni_user_id)
        eligible_accounts(alumni, identities)
        connection = pair_connection(db, user.id, alumni.user_id)
        if connection and connection.status == "BLOCKED":
            raise HTTPException(409, "This relationship is blocked. No new guidance requests are allowed.")
        if connection and connection.status == "ACTIVE":
            raise HTTPException(409, "You are already connected with this alumni.")
        if not alumni.accepting_guidance_requests:
            raise HTTPException(409, "This alumni is not accepting guidance requests right now.")
        if not db.get(GuidanceArea, payload.guidance_area_id):
            raise HTTPException(422, "Choose an existing guidance area.")
        pair = [GuidanceRequest.student_user_id == user.id, GuidanceRequest.alumni_user_id == alumni.user_id]
        if db.scalar(select(GuidanceRequest.id).where(*pair, GuidanceRequest.status == "PENDING")):
            raise HTTPException(409, "You already have a pending request for this alumni.")
        rejected_at = db.scalar(select(func.max(GuidanceRequest.responded_at)).where(*pair, GuidanceRequest.status == "REJECTED"))
        if rejected_at:
            until = utc(rejected_at) + timedelta(days=settings.REQUEST_REJECTION_COOLDOWN_DAYS)
            if now() < until:
                raise HTTPException(409, "Rejection cooldown: you may request this alumni again after " + until.isoformat() + ".")
        pending = db.scalar(select(func.count()).select_from(GuidanceRequest).where(
            GuidanceRequest.student_user_id == user.id, GuidanceRequest.status == "PENDING"))
        if pending >= settings.MAX_PENDING_GUIDANCE_REQUESTS:
            raise HTTPException(409, f"You can have at most {settings.MAX_PENDING_GUIDANCE_REQUESTS} pending requests. Cancel or wait for a response.")
        item = GuidanceRequest(student_user_id=user.id, **payload.model_dump(), status="PENDING")
        db.add(item)
        db.flush()
        notify(db, alumni.user_id, item.id, "REQUEST_RECEIVED")
    return item


def request_action(db, user, request_id, action):
    with transaction(db):
        item = db.get(GuidanceRequest, request_id)
        owner_id = item.student_user_id if item and action == "cancel" else item.alumni_user_id if item else None
        if not item or owner_id != user.id:
            raise HTTPException(404, "Guidance request not found.")
        alumni, identities = lock_pair(db, item.student_user_id, item.alumni_user_id)
        # Re-read AFTER acquiring the lock; another response may have committed.
        db.refresh(item)
        if item.status != "PENDING":
            raise HTTPException(409, "This request has already been processed.")
        stamp = now()
        if action == "accept":
            eligible_accounts(alumni, identities)
            connection = pair_connection(db, item.student_user_id, item.alumni_user_id)
            if connection and connection.status == "BLOCKED":
                raise HTTPException(409, "This relationship is blocked.")
            if connection and connection.status == "ACTIVE":
                raise HTTPException(409, "This pair is already connected.")
            item.status = "ACCEPTED"
            item.responded_at = stamp
            if not connection:
                connection = Connection(student_user_id=item.student_user_id, alumni_user_id=item.alumni_user_id)
                db.add(connection)
            connection.source_request_id = item.id
            connection.status = "ACTIVE"
            connection.connected_at = stamp
            connection.updated_at = stamp
            connection.disconnected_at = None
            connection.blocked_by_user_id = None
            connection.blocked_at = None
            db.flush()  # Connection/request integrity is checked inside this transaction.
            notify(db, item.student_user_id, item.id, "REQUEST_ACCEPTED")
        else:
            item.status = "CANCELLED" if action == "cancel" else "REJECTED"
            item.responded_at = stamp
            if action == "reject":
                notify(db, item.student_user_id, item.id, "REQUEST_REJECTED")
    return item


def connection_action(db, user, connection_id, action):
    with transaction(db):
        item = db.get(Connection, connection_id)
        if not item or user.id not in (item.student_user_id, item.alumni_user_id):
            raise HTTPException(404, "Connection not found.")
        lock_pair(db, item.student_user_id, item.alumni_user_id)
        db.refresh(item)
        change_connection(db, item, user.id, action)
    return item


def block_pair(db, user, other_id):
    with transaction(db):
        student_id, alumni_id = (user.id, other_id) if user.role == UserRole.STUDENT else (other_id, user.id)
        lock_pair(db, student_id, alumni_id)
        item = pair_connection(db, student_id, alumni_id)
        if not item:
            history = db.scalar(select(GuidanceRequest.id).where(
                GuidanceRequest.student_user_id == student_id,
                GuidanceRequest.alumni_user_id == alumni_id).limit(1))
            if not history:
                raise HTTPException(404, "No request or connection exists with this user.")
            item = Connection(student_user_id=student_id, alumni_user_id=alumni_id, status="DISCONNECTED")
            db.add(item)
        change_connection(db, item, user.id, "block")
    return item


def change_connection(db, item, user_id, action):
    stamp = now()
    if action == "disconnect":
        if item.status != "ACTIVE":
            raise HTTPException(409, "Only an active connection can be disconnected.")
        item.status = "DISCONNECTED"
        item.disconnected_at = stamp
    elif action == "unblock":
        if item.status != "BLOCKED":
            raise HTTPException(409, "This relationship is not blocked.")
        if item.blocked_by_user_id != user_id:
            raise HTTPException(403, "Only the person who blocked this relationship can unblock it.")
        item.status = "DISCONNECTED"
        item.disconnected_at = stamp
        item.blocked_by_user_id = None
        item.blocked_at = None
    else:
        if item.status == "BLOCKED":
            raise HTTPException(409, "This relationship is already blocked.")
        item.status = "BLOCKED"
        item.blocked_by_user_id = user_id
        item.blocked_at = stamp
        item.disconnected_at = stamp
        # A block invalidates pending requests without starting a rejection cooldown.
        pending = db.scalars(select(GuidanceRequest).where(
            GuidanceRequest.student_user_id == item.student_user_id,
            GuidanceRequest.alumni_user_id == item.alumni_user_id,
            GuidanceRequest.status == "PENDING")).all()
        for request in pending:
            request.status = "CANCELLED"
            request.responded_at = stamp
    item.updated_at = stamp


def people(db, ids):
    result = {}
    for user in db.scalars(select(User).where(User.id.in_(ids))):
        result[user.id] = {"user_id": user.id, "name": user.name, "role": user.role,
                           "branch": None, "graduation_year": None, "bio": None, "skills": []}
    for model in (StudentProfile, AlumniProfile):
        for profile in db.scalars(select(model).where(model.user_id.in_(ids))):
            result[profile.user_id].update(branch=profile.branch, graduation_year=profile.graduation_year, bio=profile.bio)
    for uid, skill in db.execute(select(UserSkill.user_id, Skill).join(Skill).where(UserSkill.user_id.in_(ids)).order_by(Skill.name)):
        result[uid]["skills"].append(skill)
    return result


def request_public(db, rows):
    identities = people(db, {uid for row in rows for uid in (row.student_user_id, row.alumni_user_id)})
    areas = {area.id: area for area in db.scalars(select(GuidanceArea).where(GuidanceArea.id.in_({r.guidance_area_id for r in rows})))}
    return [{
        "id": row.id, "student": identities[row.student_user_id], "alumni": identities[row.alumni_user_id],
        "guidance_area": areas[row.guidance_area_id], "message": row.message, "status": row.status,
        "created_at": utc(row.created_at), "responded_at": utc(row.responded_at),
        "cooldown_until": utc(row.responded_at) + timedelta(days=settings.REQUEST_REJECTION_COOLDOWN_DAYS)
            if row.status == "REJECTED" else None,
    } for row in rows]


def connection_public(db, rows):
    from app.models.messaging import Conversation
    conversations = dict(db.execute(select(Conversation.connection_id, Conversation.id).where(
        Conversation.connection_id.in_([row.id for row in rows]))).all())
    identities = people(db, {uid for row in rows for uid in (row.student_user_id, row.alumni_user_id)})
    return [{
        "id": row.id, "student": identities[row.student_user_id], "alumni": identities[row.alumni_user_id],
        "source_request_id": row.source_request_id, "status": row.status, "conversation_id": conversations.get(row.id),
        "connected_at": utc(row.connected_at), "updated_at": utc(row.updated_at),
        "disconnected_at": utc(row.disconnected_at), "blocked_at": utc(row.blocked_at),
        "blocked_by_user_id": row.blocked_by_user_id,
    } for row in rows]
