"""Private REST messaging. Reuse the Phase 4 pair lock before changing state."""
from math import ceil
from fastapi import HTTPException
from sqlalchemy import func, select, update
from app.models import AccountStatus, User
from app.models.messaging import Conversation, Message
from app.models.networking import Connection, Notification
from app.services.networking import lock_pair, transaction, now, people, utc


def participation(user_id):
    return (Connection.student_user_id == user_id) | (Connection.alumni_user_id == user_id)


def owned_connection(db, user, connection_id):
    item = db.scalar(select(Connection).where(Connection.id == connection_id, participation(user.id)))
    if not item:
        raise HTTPException(404, "Connection not found.")
    return item


def owned_conversation(db, user, conversation_id):
    row = db.execute(select(Conversation, Connection).join(Connection, Conversation.connection_id == Connection.id)
                     .where(Conversation.id == conversation_id, participation(user.id))).first()
    if not row:
        raise HTTPException(404, "Conversation not found.")
    return row


def lock_connection(db, connection):
    _, identities = lock_pair(db, connection.student_user_id, connection.alumni_user_id)
    db.refresh(connection)
    return identities


def send_allowed(connection, identities):
    if connection.status != "ACTIVE":
        raise HTTPException(409, "This connection is " + connection.status.lower() + ". Previous messages remain readable; new messages are not allowed.")
    if any(person.account_status != AccountStatus.ACTIVE for person in identities.values()):
        raise HTTPException(409, "Messaging is unavailable while a participant's account is inactive.")


def open_conversation(db, user, connection_id):
    with transaction(db):
        connection = owned_connection(db, user, connection_id)
        identities = lock_connection(db, connection)
        conversation = db.scalar(select(Conversation).where(Conversation.connection_id == connection.id))
        if not conversation:
            send_allowed(connection, identities)
            conversation = Conversation(connection_id=connection.id)
            db.add(conversation)
            db.flush()
    return conversation


def message_notification(db, conversation, recipient_id, sender_name):
    # Pair lock serializes send/read operations; the partial unique index is the final guard.
    note = db.scalar(select(Notification).where(Notification.user_id == recipient_id,
        Notification.conversation_id == conversation.id, Notification.type == "MESSAGE_RECEIVED",
        Notification.is_read.is_(False)).with_for_update())
    if not note:
        db.add(Notification(user_id=recipient_id, conversation_id=conversation.id,
                            type="MESSAGE_RECEIVED", message="New message from " + sender_name))
    else:
        note.message = "New message from " + sender_name
        note.created_at = now()


def send_message(db, user, conversation_id, payload):
    with transaction(db):
        conversation, connection = owned_conversation(db, user, conversation_id)
        identities = lock_connection(db, connection)
        send_allowed(connection, identities)
        stamp = now()
        item = Message(conversation_id=conversation.id, sender_user_id=user.id,
                       content=payload.content, created_at=stamp)
        db.add(item)
        conversation.updated_at = stamp
        db.flush()
        recipient = connection.alumni_user_id if user.id == connection.student_user_id else connection.student_user_id
        message_notification(db, conversation, recipient, identities[user.id].name)
    return item


def mark_read(db, user, conversation_id, through_id):
    with transaction(db):
        conversation, connection = owned_conversation(db, user, conversation_id)
        lock_connection(db, connection)
        boundary = db.scalar(select(Message.id).where(Message.id == through_id, Message.conversation_id == conversation.id))
        if boundary is None:
            raise HTTPException(422, "Read boundary must belong to this conversation.")
        # Only messages received by this participant are marked; newly arrived messages remain unread.
        db.execute(update(Message).where(Message.conversation_id == conversation.id,
            Message.id <= through_id, Message.sender_user_id != user.id, Message.read_at.is_(None))
            .values(read_at=now()))
        unread = db.scalar(select(func.count()).select_from(Message).where(
            Message.conversation_id == conversation.id, Message.sender_user_id != user.id, Message.read_at.is_(None)))
        if not unread:
            db.execute(update(Notification).where(Notification.user_id == user.id,
                Notification.conversation_id == conversation.id, Notification.type == "MESSAGE_RECEIVED",
                Notification.is_read.is_(False)).values(is_read=True))
    return {"unread_count": unread}


def summaries(db, user, rows):
    if not rows:
        return []
    ids = [row.id for row in rows]
    connections = {c.id:c for c in db.scalars(select(Connection).where(Connection.id.in_([r.connection_id for r in rows])))}
    peer_ids = {c.alumni_user_id if c.student_user_id == user.id else c.student_user_id for c in connections.values()}
    peers = people(db, peer_ids)
    active = set(db.scalars(select(User.id).where(User.id.in_(peer_ids), User.account_status == AccountStatus.ACTIVE)))
    latest = select(Message.conversation_id, func.max(Message.id).label("last_id")).where(Message.conversation_id.in_(ids)).group_by(Message.conversation_id).subquery()
    previews = {m.conversation_id:m.content[:160] for m in db.scalars(select(Message).join(latest, Message.id == latest.c.last_id))}
    unread = dict(db.execute(select(Message.conversation_id, func.count()).where(
        Message.conversation_id.in_(ids), Message.sender_user_id != user.id, Message.read_at.is_(None)).group_by(Message.conversation_id)).all())
    result = []
    for row in rows:
        connection = connections[row.connection_id]
        peer_id = connection.alumni_user_id if connection.student_user_id == user.id else connection.student_user_id
        result.append({"id":row.id, "connection_id":connection.id, "connection_status":connection.status,
            "other_participant":peers[peer_id], "created_at":utc(row.created_at), "updated_at":utc(row.updated_at),
            "last_message_preview":previews.get(row.id), "unread_count":unread.get(row.id,0),
            "can_send":connection.status == "ACTIVE" and peer_id in active})
    return result


def history(db, user, conversation_id, page, page_size, snapshot_id):
    owned_conversation(db, user, conversation_id)
    if snapshot_id is not None and not db.scalar(select(Message.id).where(
            Message.conversation_id == conversation_id, Message.id == snapshot_id)):
        raise HTTPException(422, "History snapshot must belong to this conversation.")
    if snapshot_id is None:
        snapshot_id = db.scalar(select(func.max(Message.id)).where(Message.conversation_id == conversation_id))
    query = select(Message).where(Message.conversation_id == conversation_id, Message.id <= (snapshot_id or 0))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc())
                          .offset((page-1)*page_size).limit(page_size)))
    rows.reverse()
    return {"items":rows, "page":page, "page_size":page_size, "total_results":total,
            "total_pages":ceil(total/page_size), "snapshot_id":snapshot_id}

