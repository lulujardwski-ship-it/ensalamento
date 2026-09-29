"""Exercise actual rollback and concurrent optimistic writes on both supported stores."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from server.store import Store, StaleRevision


@pytest.fixture(params=['sqlite', 'postgres'])
def store(request, tmp_path):
    if request.param == 'postgres':
        url = os.getenv('TEST_POSTGRES_URL')
        if not url:
            pytest.skip('TEST_POSTGRES_URL not set; PostgreSQL coverage runs in CI')
    else:
        url = 'sqlite:///' + str(tmp_path / 'transactions.db')
    return Store(url)


def test_failed_transaction_preserves_document_and_revision(store):
    before_revision, before = store.read()

    def invalid_change(state):
        state['settings']['transaction_probe'] = 'must-not-persist'
        raise ValueError('business validation failed')

    with pytest.raises(ValueError, match='business validation failed'):
        store.update(before_revision, invalid_change)
    assert store.read() == (before_revision, before)


def test_concurrent_stale_writers_cannot_overwrite_each_other(store):
    revision, _ = store.read()
    ready = Barrier(2)

    def writer(value):
        ready.wait(timeout=5)
        try:
            def change(state):
                state['settings']['concurrency_probe'] = value
                return value
            new_revision, _ = store.update(revision, change)
            return ('accepted', value, new_revision)
        except StaleRevision:
            return ('stale', value, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, ['first', 'second']))
    accepted = [r for r in results if r[0] == 'accepted']
    stale = [r for r in results if r[0] == 'stale']
    assert len(accepted) == len(stale) == 1
    after_revision, state = store.read()
    assert after_revision == revision + 1
    assert state['settings']['concurrency_probe'] == accepted[0][1]


def test_postgres_application_data_is_outside_public_schema(store):
    if not store.postgres:
        pytest.skip('PostgreSQL-specific schema boundary')
    with store.connection() as conn:
        actual = conn.execute("SELECT to_regclass('ensalamento.application_state')").fetchone()[0]
        public = conn.execute("SELECT to_regclass('public.application_state')").fetchone()[0]
    assert actual is not None
    assert public is None


def test_multiple_postgres_workers_initialize_without_losing_data():
    url = os.getenv('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TEST_POSTGRES_URL not set; PostgreSQL coverage runs in CI')
    original = Store(url)
    original.update(None, lambda state: state['settings'].update(boot_probe='preserved'))
    before = original.read()
    ready = Barrier(8)

    def boot_worker(_):
        ready.wait(timeout=10)
        return Store(url).read()

    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(3):
            assert list(pool.map(boot_worker, range(8))) == [before] * 8
    assert original.read() == before
