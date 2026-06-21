from backend.db.database import get_engine_kwargs


def test_psycopg_postgres_disables_prepared_statements():
    kwargs = get_engine_kwargs("postgresql+psycopg://user:pass@host:6543/postgres")

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300
    assert kwargs["pool_timeout"] == 10
    assert kwargs["pool_size"] == 2
    assert kwargs["max_overflow"] == 1
    assert kwargs["pool_use_lifo"] is True
    assert kwargs["connect_args"]["prepare_threshold"] is None
    assert kwargs["connect_args"]["connect_timeout"] == 10
    assert "statement_timeout=8000" in kwargs["connect_args"]["options"]
    assert "idle_in_transaction_session_timeout=15000" in kwargs["connect_args"]["options"]


def test_postgres_urls_use_bounded_pool_and_connect_timeout():
    kwargs = get_engine_kwargs("postgresql://user:pass@host:5432/postgres")

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300
    assert kwargs["pool_timeout"] == 10
    assert kwargs["pool_size"] == 2
    assert kwargs["max_overflow"] == 1
    assert kwargs["pool_use_lifo"] is True
    assert kwargs["connect_args"]["connect_timeout"] == 10
    assert "statement_timeout=8000" in kwargs["connect_args"]["options"]
    assert "idle_in_transaction_session_timeout=15000" in kwargs["connect_args"]["options"]


def test_non_psycopg_urls_do_not_receive_psycopg_connect_args():
    kwargs = get_engine_kwargs("sqlite://")

    assert kwargs == {"pool_pre_ping": True}
