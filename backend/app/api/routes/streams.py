from fastapi import APIRouter

from app.api.deps import CatalogDep, ClientDep, SessionDep, SettingsDep
from app.core.errors import NotFoundError
from app.models import Stream
from app.repositories import StreamRepository
from app.schemas.api import AddOfferIn, PushResultOut, StreamOut, StreamPushOut, UpdateOfferIn
from app.services.publish_service import PublishService
from app.services.stream_editor import StreamEditor

router = APIRouter(prefix="/streams", tags=["streams"])


async def load_stream(session: SessionDep, stream_id: int, *, lock: bool = False) -> Stream:
    repo = StreamRepository(session)
    stream = await (repo.get_for_update(stream_id) if lock else repo.get(stream_id))
    if stream is None:
        raise NotFoundError(f"Поток {stream_id} не найден в обёртке.")
    return stream


async def _done(session: SessionDep, stream: Stream) -> StreamOut:
    await session.flush()
    await session.refresh(stream, attribute_names=["offers"])
    return StreamOut.build(stream)


@router.get("/{stream_id}", response_model=StreamOut)
async def get_stream(stream_id: int, session: SessionDep) -> StreamOut:
    return StreamOut.build(await load_stream(session, stream_id))


@router.post("/{stream_id}/offers", response_model=StreamOut)
async def add_offer(
    stream_id: int, body: AddOfferIn, session: SessionDep, catalog: CatalogDep
) -> StreamOut:
    """ADD: добавить оффер по ID (локально, до публикации)."""
    stream = await load_stream(session, stream_id)
    await StreamEditor(catalog).add_offer(stream, body.offer_id)
    return await _done(session, stream)


@router.post("/{stream_id}/offers/{link_id}/remove", response_model=StreamOut)
async def remove_offer(
    stream_id: int, link_id: int, session: SessionDep, catalog: CatalogDep
) -> StreamOut:
    """REMOVE: оффер серый, 0%, остальные доли пересчитываются."""
    stream = await load_stream(session, stream_id)
    StreamEditor(catalog).remove(stream, link_id)
    return await _done(session, stream)


@router.post("/{stream_id}/offers/{link_id}/restore", response_model=StreamOut)
async def restore_offer(
    stream_id: int, link_id: int, session: SessionDep, catalog: CatalogDep
) -> StreamOut:
    """BRING BACK: вернуть архивный оффер в поток."""
    stream = await load_stream(session, stream_id)
    StreamEditor(catalog).restore(stream, link_id)
    return await _done(session, stream)


@router.patch("/{stream_id}/offers/{link_id}", response_model=StreamOut)
async def update_offer(
    stream_id: int, link_id: int, body: UpdateOfferIn, session: SessionDep, catalog: CatalogDep
) -> StreamOut:
    """Закрепить/открепить долю или задать её вручную (ручная доля закрепляется)."""
    stream = await load_stream(session, stream_id)
    editor = StreamEditor(catalog)
    if body.share is not None:
        editor.set_share(stream, link_id, body.share)
    elif body.pinned is not None:
        editor.set_pinned(stream, link_id, body.pinned)
    return await _done(session, stream)


@router.post("/{stream_id}/rebalance", response_model=StreamOut)
async def rebalance(stream_id: int, session: SessionDep, catalog: CatalogDep) -> StreamOut:
    """Выровнять доли (например, если в Keitaro сумма стала не 100%)."""
    stream = await load_stream(session, stream_id)
    StreamEditor(catalog).rebalance(stream)
    return await _done(session, stream)


@router.post("/{stream_id}/cancel", response_model=StreamOut)
async def cancel(stream_id: int, session: SessionDep, catalog: CatalogDep) -> StreamOut:
    """CANCEL: отменить неопубликованные изменения."""
    stream = await load_stream(session, stream_id)
    StreamEditor(catalog).cancel(stream)
    return await _done(session, stream)


@router.post("/{stream_id}/push", response_model=StreamPushOut)
async def push(
    stream_id: int,
    session: SessionDep,
    client: ClientDep,
    settings: SettingsDep,
    force: bool = False,
) -> StreamPushOut:
    """PUSH TO KT для одного потока."""
    stream = await load_stream(session, stream_id, lock=True)
    result = await PublishService(client, settings).push_stream(
        stream.campaign, stream, force=force
    )
    return StreamPushOut(
        result=PushResultOut(
            stream_id=result.stream_id, changed=result.changed, message=result.message
        ),
        stream=await _done(session, stream),
    )
