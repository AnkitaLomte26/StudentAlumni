from math import ceil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User
from app.models.networking import Connection, GuidanceRequest, Notification
from app.routes.professional import member, trusted_origin
from app.schemas.networking import (BlockCreate, ConnectionPage, ConnectionPublic, ConnectionStatus,
    NotificationPage, NotificationPublic, PersonPublic, RequestCreate, RequestPage, RequestPublic, RequestStatus)
from app.services import networking as service
from app.utils.deps import get_current_user, require_alumni, require_student

router = APIRouter(prefix="/api", tags=["guidance and connections"], dependencies=[Depends(trusted_origin)])


@router.post("/guidance-requests", response_model=RequestPublic, status_code=201)
def create(payload: RequestCreate, db: Session = Depends(get_db), user: User = Depends(require_student)):
    return service.request_public(db, [service.create_request(db, user, payload)])[0]


def request_page(db, user, incoming, status, page, page_size):
    ownership = GuidanceRequest.alumni_user_id == user.id if incoming else GuidanceRequest.student_user_id == user.id
    query = select(GuidanceRequest).where(ownership)
    pending = db.scalar(select(func.count()).select_from(GuidanceRequest).where(ownership, GuidanceRequest.status == "PENDING"))
    if status:
        query = query.where(GuidanceRequest.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(GuidanceRequest.created_at.desc(), GuidanceRequest.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": service.request_public(db, rows), "page": page, "page_size": page_size,
            "total_results": total, "total_pages": ceil(total/page_size), "pending_count": pending,
            "pending_limit": settings.MAX_PENDING_GUIDANCE_REQUESTS}


@router.get("/guidance-requests/my", response_model=RequestPage)
def outgoing(status: RequestStatus | None = None, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
             db: Session = Depends(get_db), user: User = Depends(require_student)):
    return request_page(db, user, False, status, page, page_size)


@router.get("/guidance-requests/incoming", response_model=RequestPage)
def incoming(status: RequestStatus | None = None, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
             db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    return request_page(db, user, True, status, page, page_size)


@router.get("/guidance-requests/{request_id}/student-profile", response_model=PersonPublic)
def student_profile(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    item = db.get(GuidanceRequest, request_id)
    if not item or item.alumni_user_id != user.id:
        raise HTTPException(404, "Guidance request not found.")
    return service.people(db, [item.student_user_id])[item.student_user_id]


@router.patch("/guidance-requests/{request_id}/cancel", response_model=RequestPublic)
def cancel(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_student)):
    return service.request_public(db, [service.request_action(db, user, request_id, "cancel")])[0]


@router.patch("/guidance-requests/{request_id}/accept", response_model=RequestPublic)
def accept(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    return service.request_public(db, [service.request_action(db, user, request_id, "accept")])[0]


@router.patch("/guidance-requests/{request_id}/reject", response_model=RequestPublic)
def reject(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_alumni)):
    return service.request_public(db, [service.request_action(db, user, request_id, "reject")])[0]


@router.get("/connections", response_model=ConnectionPage)
def connections(status: ConnectionStatus | None = None, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
                db: Session = Depends(get_db), user: User = Depends(member)):
    query = select(Connection).where((Connection.student_user_id == user.id) | (Connection.alumni_user_id == user.id))
    if status:
        query = query.where(Connection.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Connection.updated_at.desc(), Connection.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": service.connection_public(db, rows), "page": page, "page_size": page_size,
            "total_results": total, "total_pages": ceil(total/page_size)}


@router.post("/connections/block", response_model=ConnectionPublic)
def block_other(payload: BlockCreate, db: Session = Depends(get_db), user: User = Depends(member)):
    return service.connection_public(db, [service.block_pair(db, user, payload.other_user_id)])[0]


@router.patch("/connections/{connection_id}/disconnect", response_model=ConnectionPublic)
def disconnect(connection_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    return service.connection_public(db, [service.connection_action(db, user, connection_id, "disconnect")])[0]


@router.patch("/connections/{connection_id}/block", response_model=ConnectionPublic)
def block(connection_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    return service.connection_public(db, [service.connection_action(db, user, connection_id, "block")])[0]


@router.patch("/connections/{connection_id}/unblock", response_model=ConnectionPublic)
def unblock(connection_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    return service.connection_public(db, [service.connection_action(db, user, connection_id, "unblock")])[0]


@router.get("/notifications", response_model=NotificationPage)
def notifications(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Notification).where(Notification.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)))
    rows = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": rows, "unread_count": unread, "page": page, "page_size": page_size,
            "total_results": total, "total_pages": ceil(total/page_size)}


@router.patch("/notifications/{notification_id}/read", response_model=NotificationPublic)
def read_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    with service.transaction(db):
        item = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id).with_for_update())
        if not item:
            raise HTTPException(404, "Notification not found.")
        item.is_read = True
    return item
