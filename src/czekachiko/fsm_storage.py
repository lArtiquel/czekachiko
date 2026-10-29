from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from czekachiko.db.models import FsmRow


class PgStorage(BaseStorage):
    """FSM state in Postgres, so a restart never loses a half-finished flow."""

    def __init__(self, factory: async_sessionmaker):
        self.factory = factory

    @staticmethod
    def _key(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with self.factory() as s:
            await s.execute(
                insert(FsmRow)
                .values(key=self._key(key), state=value, data={})
                .on_conflict_do_update(index_elements=["key"], set_={"state": value})
            )
            await s.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.factory() as s:
            row = await s.get(FsmRow, self._key(key))
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        async with self.factory() as s:
            await s.execute(
                insert(FsmRow)
                .values(key=self._key(key), state=None, data=data)
                .on_conflict_do_update(index_elements=["key"], set_={"data": data})
            )
            await s.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.factory() as s:
            row = await s.get(FsmRow, self._key(key))
            return dict(row.data) if row else {}

    async def close(self) -> None:
        pass
