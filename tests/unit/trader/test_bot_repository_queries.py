from sqlalchemy.dialects import postgresql

from trader.infra.db.bot_postgres_repository import BotPostgresRepository


class _CapturingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement

        class _Result:
            def scalars(self_inner):
                class _S:
                    def all(self_s):
                        return []
                return _S()
        return _Result()


async def test_find_needing_processing_includes_inactive_bots_with_active_trades():
    session = _CapturingSession()
    await BotPostgresRepository(session).find_needing_processing()
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "bot_configs.is_active IS true OR (EXISTS" in sql
    assert "trades.status IN" in sql
