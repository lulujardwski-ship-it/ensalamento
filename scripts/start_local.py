"""Start the explicitly local, fictional demonstration on http://127.0.0.1:8000."""
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    # Deliberately ignore production URLs/credentials: this launcher uses its own local database.
    os.environ['APP_ENV'] = 'development'
    os.environ['DEV_LOGIN_ENABLED'] = 'true'
    os.environ['TRUST_PROXY'] = 'false'
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(ROOT / 'instance' / 'demo.sqlite3')
    os.environ['SECRET_KEY'] = secrets.token_urlsafe(48)
    for name in ('ADMIN_EMAILS', 'ALLOWED_DOMAINS', 'FRONTEND_URL', 'GOOGLE_CLIENT_ID',
                 'GOOGLE_CLIENT_SECRET', 'MICROSOFT_CLIENT_ID', 'MICROSOFT_CLIENT_SECRET',
                 'MICROSOFT_TENANT_ID'):
        os.environ[name] = ''
    from server.app import create_app
    app = create_app()
    store = app.extensions['store']
    _, state = store.read()
    if not any(state[key] for key in ('users', 'periods', 'classes', 'versions')):
        result = app.test_cli_runner().invoke(args=['seed-demo'])
        if result.exit_code:
            raise RuntimeError(result.output)
        print(result.output.strip())
    print('DEMONSTRACAO LOCAL: dados ficticios, sem login federado de producao.')
    print('Abra http://127.0.0.1:8000 — Ctrl+C encerra o servidor.')
    app.run(host='127.0.0.1', port=8000, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
