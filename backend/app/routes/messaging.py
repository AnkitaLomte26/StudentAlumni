from math import ceil
from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from app.services.realtime import manager
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.models.messaging import Conversation
from app.models.networking import Connection
from app.routes.professional import member, trusted_origin
from app.schemas.messaging import ConversationPublic, ConversationPage, MessageCreate, MessagePublic, MessagePage, ReadInput
from app.services import messaging as service

router = APIRouter(prefix="/api", tags=["private messaging"], dependencies=[Depends(trusted_origin)])


@router.post("/connections/{connection_id}/conversation", response_model=ConversationPublic)
def open_conversation(connection_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    return service.summaries(db, user, [service.open_conversation(db, user, connection_id)])[0]


@router.get("/conversations", response_model=ConversationPage)
def conversations(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
                  db: Session = Depends(get_db), user: User = Depends(member)):
    query = select(Conversation).join(Connection).where(service.participation(user.id))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                     .offset((page-1)*page_size).limit(page_size)).all()
    return {"items":service.summaries(db, user, rows), "page":page, "page_size":page_size,
            "total_results":total, "total_pages":ceil(total/page_size)}


@router.get("/conversations/{conversation_id}", response_model=ConversationPublic)
def detail(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(member)):
    conversation, _ = service.owned_conversation(db, user, conversation_id)
    return service.summaries(db, user, [conversation])[0]


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
def history(conversation_id: int, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=50),
            snapshot_id: int | None = Query(None, gt=0), db: Session = Depends(get_db), user: User = Depends(member)):
    return service.history(db, user, conversation_id, page, page_size, snapshot_id)


@router.post("/conversations/{conversation_id}/messages", response_model=MessagePublic, status_code=201)
async def send(conversation_id: int, payload: MessageCreate, db: Session = Depends(get_db), user: User = Depends(member)):
    def persist():
        item = service.send_message(db, user, conversation_id, payload)
        return MessagePublic.model_validate(item).model_dump(mode="json")
    message = await run_in_threadpool(persist)
    # The common service has committed before any live event is published.
    await manager.publish(conversation_id, message)
    return message


@router.patch("/conversations/{conversation_id}/read")
def read(conversation_id: int, payload: ReadInput, db: Session = Depends(get_db), user: User = Depends(member)):
    return service.mark_read(db, user, conversation_id, payload.through_message_id)
