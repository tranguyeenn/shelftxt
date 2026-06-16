from backend.db.database import get_engine_kwargs


def test_psycopg_postgres_disables_prepared_statements():
    kwargs = get_engine_kwargs("postgresql+psycopg://user:pass@host:6543/postgres")

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["connect_args"]["prepare_threshold"] is None


def test_non_psycopg_urls_do_not_receive_psycopg_connect_args():
    kwargs = get_engine_kwargs("sqlite://")

    assert kwargs == {"pool_pre_ping": True}
