"""Regressões de validação encontradas durante a revisão integrada."""
import copy

from test_server import app, client, login, bootstrap, post


def test_cancelling_class_by_edit_removes_only_draft_allocations(client):
    login(client)
    before = bootstrap(client)
    record = copy.deepcopy(before['classes'][0])
    ids = {m['id'] for m in before['meetings'] if m['class_id'] == record['id']}
    record['status'] = 'cancelled'
    response = post(client, '/api/entities/classes', {'record': record, 'reason': 'Cancelamento revisado.'})
    assert response.status_code == 200
    after = bootstrap(client)
    assert all(a['meeting_id'] not in ids for a in after['allocations'])
    assert before['published_version'] == after['published_version']
    login(client, 'student')
    assert any(a['meeting_id'] in ids for a in bootstrap(client)['allocations'])


def test_csv_capacity_error_identifies_column(client):
    login(client)
    room = bootstrap(client)['rooms'][0]
    source = 'id,code,name,campus_id,building_id,capacity\n' + ','.join([
        'import-test', 'IMPORT-TEST', 'Sala importada', room['campus_id'], room['building_id'], '-1'])
    response = post(client, '/api/import/preview', {'entity': 'rooms', 'csv': source})
    report = response.get_json()
    assert response.status_code == 200
    assert report['token'] is None
    assert report['errors'][0]['line'] == 2
    assert report['errors'][0]['field'] == 'capacity'


def test_publish_cancellation_of_last_classes(client):
    login(client)
    for record in bootstrap(client)['classes']:
        record['status'] = 'cancelled'
        assert post(client, '/api/entities/classes', {'record': record}).status_code == 200
    response = post(client, '/api/publish', {'description': 'Cancelamento de todas as aulas', 'reason': 'Revisão do calendário.'})
    assert response.status_code == 200, response.get_json()
    login(client, 'student')
    result = bootstrap(client)
    assert result['classes'] == result['meetings'] == result['allocations'] == []
    assert result['published_version']['number'] == 2


def test_coordinator_official_view_preserves_snapshot_and_scope(app, client):
    login(client, 'coordinator')
    before = client.get('/api/bootstrap?view=published').get_json()
    assert before['mode'] == 'published'
    scope = set(before['user']['course_ids'])
    assert before['classes'] and all(c['course_id'] in scope for c in before['classes'])
    def change(state):
        for klass in state['classes']:
            klass['name'] = 'Alteração ainda não publicada'
        for user in state['users']:
            if user['role'] == 'teacher':
                user['name'] = 'Nome alterado no rascunho'
    app.extensions['store'].update(None, change)
    official = client.get('/api/bootstrap?view=published').get_json()
    assert official['classes'] == before['classes']
    assert official['teachers'] == before['teachers']
    assert official['teachers']
    assert all(set(t) == {'id', 'name', 'email'} for t in official['teachers'])
    draft = bootstrap(client)
    assert draft['mode'] == 'draft'
    assert all(c['name'] == 'Alteração ainda não publicada' for c in draft['classes'])


def test_default_published_period_prefers_current_over_future(app, client):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    def configure(state):
        current = state['periods'][0]
        current['start_date'] = (today - timedelta(days=10)).isoformat()
        current['end_date'] = (today + timedelta(days=10)).isoformat()
        future = {**current, 'id': 'future', 'code': 'FUTURE', 'start_date': (today + timedelta(days=30)).isoformat(), 'end_date': (today + timedelta(days=100)).isoformat()}
        state['periods'].append(future)
        version = copy.deepcopy(state['versions'][0])
        version.update(id='future-version', period_id='future')
        version['snapshot']['periods'] = [future]
        state['versions'].append(version)
        state['active_versions']['future'] = 'future-version'
    app.extensions['store'].update(None, configure)
    login(client, 'student')
    result = bootstrap(client)
    assert result['period_id'] != 'future'
