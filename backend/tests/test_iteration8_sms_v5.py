"""Iteration 8 — build 2026.09.04-sms-v5 backend tests.

Focus: new /health env-report block, admin diagnostics server_env, built-in-default
subprocess simulation, and a quick regression on core auth/product endpoints.
"""
import json
import os
import subprocess

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL') or os.environ.get('EXPO_BACKEND_URL')
if BASE_URL is None:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('EXPO_PUBLIC_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().strip('"')
BASE_URL = BASE_URL.rstrip('/')
API = f"{BASE_URL}/api"

EXPECTED_BUILD = "2026.09.04-sms-v5"
EXPECTED_TEMPLATE_ID = "61baece18e964726da04e8c5"

BACKEND_ENV = dotenv_values('/app/backend/.env')
SECRET_AUTHKEY = BACKEND_ENV.get('MSG91_AUTHKEY', '')
SECRET_JWT = BACKEND_ENV.get('JWT_SECRET', '')


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{API}/auth/send-otp", json={"phone": "9999999999"})
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/auth/verify-otp", json={"phone": "9999999999", "otp": "1234"})
    assert r.status_code == 200, r.text
    data = r.json()
    return data.get('token') or data.get('access_token')


# ---------- /api/health public v5 fields ----------
class TestHealthV5:
    def test_health_v5_shape_and_no_secrets(self, s):
        r = s.get(f"{API}/health")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get('build') == EXPECTED_BUILD, data
        assert data.get('provider_check') == 'ok', data
        for k in ('env_keys_present', 'env_keys_missing', 'template_source',
                  'jwt_secret_configured', 'demo_phones_count', 'warnings'):
            assert k in data, f"missing {k} in /health"
        assert isinstance(data['env_keys_present'], list)
        for req in ('MSG91_AUTHKEY', 'MSG91_TEMPLATE_ID', 'JWT_SECRET',
                    'MONGO_URL', 'DB_NAME', 'OTP_DEMO_PHONES'):
            assert req in data['env_keys_present'], f"{req} not in env_keys_present"
        assert data['env_keys_missing'] == [], data['env_keys_missing']
        assert data['template_source'] == 'env'
        assert data['jwt_secret_configured'] is True
        assert data['demo_phones_count'] == 6, data['demo_phones_count']
        assert data['warnings'] == [], data['warnings']

        # No secret VALUES anywhere in response text
        body = r.text
        assert SECRET_AUTHKEY and SECRET_AUTHKEY not in body, "MSG91 authkey value leaked!"
        assert 'mongodb://' not in body.lower(), "mongodb URI leaked!"
        assert 'sk-emergent' not in body, "emergent LLM key leaked!"
        assert SECRET_JWT and SECRET_JWT not in body, "JWT secret leaked!"

        # No key named authkey/authkey_hint
        assert 'authkey' not in data, "authkey key must not be exposed on /health"
        assert 'authkey_hint' not in data, "authkey_hint must not be exposed on /health"


# ---------- /api/admin/sms/diagnostics server_env ----------
class TestAdminDiagnosticsV5:
    def test_diag_has_server_env(self, s, admin_token):
        r = s.get(f"{API}/admin/sms/diagnostics",
                  headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get('build') == EXPECTED_BUILD
        assert data.get('provider_check') == 'ok'
        assert data.get('template_id') == EXPECTED_TEMPLATE_ID
        env = data.get('server_env')
        assert isinstance(env, dict), "server_env missing"
        for k in ('env_keys_present', 'env_keys_missing', 'template_source',
                  'jwt_secret_configured', 'demo_phones_count', 'warnings'):
            assert k in env, f"server_env missing {k}"
        assert env['template_source'] == 'env'
        assert env['jwt_secret_configured'] is True


# ---------- Built-in-default subprocess simulation ----------
class TestBuiltInDefaultSubprocess:
    def test_subprocess_default_template(self):
        script = (
            "import os; from dotenv import dotenv_values; "
            "v=dotenv_values('.env'); "
            "os.environ.update({'MONGO_URL':v['MONGO_URL'],'DB_NAME':v['DB_NAME'],'MSG91_AUTHKEY':v['MSG91_AUTHKEY']}); "
            "import dotenv; dotenv.load_dotenv=lambda *a,**k: False; "
            "import asyncio, server, json; "
            "r=server._server_env_report(); "
            "pre=asyncio.run(server._msg91_preflight(force=True)); "
            "print(json.dumps({'template':server.MSG91_TEMPLATE_ID,"
            "'from_env':server.MSG91_TEMPLATE_FROM_ENV,'missing':r['env_keys_missing'],"
            "'source':r['template_source'],'warnings':r['warnings'],"
            "'preflight_ok':pre['ok'],'preflight_error':pre.get('error')}))"
        )
        env = {**os.environ}
        for k in ('MSG91_TEMPLATE_ID', 'JWT_SECRET', 'OTP_DEMO_PHONES'):
            env.pop(k, None)
        proc = subprocess.run(
            ['python3', '-c', script],
            cwd='/app/backend', env=env, capture_output=True, text=True, timeout=30
        )
        assert proc.returncode == 0, f"subprocess failed: {proc.stderr}"
        # take last non-empty stdout line (server module logs before print)
        last = [ln for ln in proc.stdout.strip().splitlines() if ln.strip().startswith('{')][-1]
        out = json.loads(last)
        assert out['template'] == EXPECTED_TEMPLATE_ID, out
        assert out['from_env'] is False, out
        assert out['source'] == 'built-in default', out
        assert 'MSG91_TEMPLATE_ID' in out['missing'], out
        joined = ' | '.join(out['warnings'])
        assert 'built-in default' in joined, f"no built-in-default warning: {out['warnings']}"
        assert any('JWT_SECRET' in w for w in out['warnings']), f"no JWT warning: {out['warnings']}"
        assert any('OTP_DEMO_PHONES' in w for w in out['warnings']), f"no demo warning: {out['warnings']}"
        assert out['preflight_ok'] is True, f"preflight failed: {out.get('preflight_error')}"


# ---------- Quick regression ----------
class TestRegression:
    def test_send_otp_demo(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": "8888888888"})
        assert r.status_code == 200, r.text

    def test_verify_otp_demo(self, s):
        r = s.post(f"{API}/auth/verify-otp", json={"phone": "8888888888", "otp": "1234"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert (data.get('token') or data.get('access_token')), data

    def test_send_otp_unknown(self, s):
        r = s.post(f"{API}/auth/send-otp", json={"phone": "9876501234"})
        assert r.status_code == 404, r.text

    def test_products(self, s):
        r = s.get(f"{API}/products?limit=3")
        assert r.status_code == 200, r.text
        data = r.json()
        assert 'products' in data
        assert len(data['products']) <= 3
