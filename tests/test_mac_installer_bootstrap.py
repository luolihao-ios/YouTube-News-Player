"""Mac 安装器证书准备的离线安全回归测试，不连接 Apple。"""
import base64
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / '.test-tools').is_dir():
    sys.path.insert(0, str(ROOT / '.test-tools'))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from nacl.public import PrivateKey, SealedBox

OPENSSL = shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'


def module():
    path = ROOT / 'scripts/bootstrap_mac_installer.py'
    if not path.exists():
        raise AssertionError('尚未实现 Mac 安装器证书准备脚本')
    spec = importlib.util.spec_from_file_location('bootstrap_mac_installer', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class FakeAPI:
    def __init__(self, existing=0, reject=False):
        self.calls = []
        self.existing = existing
        self.reject = reject

    def all(self, path):
        self.calls.append(('GET', path))
        if path != 'certificates?filter%5BcertificateType%5D=MAC_INSTALLER_DISTRIBUTION&limit=200':
            raise AssertionError('没有限定安装器证书查询')
        return [{'id': f'old-{index}', 'attributes': {
            'certificateType': 'MAC_INSTALLER_DISTRIBUTION',
            'expirationDate': '2030-01-01T00:00:00Z',
            'certificateContent': 'PUBLIC-CONTENT-MUST-NOT-BE-REPORTED',
        }} for index in range(self.existing)]

    def call(self, path, method='GET', data=None):
        self.calls.append((method, path))
        if (path, method) != ('certificates', 'POST'):
            raise AssertionError('禁止删除或撤销证书')
        if self.reject:
            raise RuntimeError('Apple HTTP 409 PRIVATE-SECRET-MUST-NOT-LEAK')
        attrs = data['data']['attributes']
        if attrs['certificateType'] != 'MAC_INSTALLER_DISTRIBUTION':
            raise AssertionError('错误的证书类型')
        csr = x509.load_pem_x509_csr(attrs['csrContent'].encode())
        self.csr = csr
        issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(csr.subject)
                .public_key(csr.public_key()).serial_number(1)
                .not_valid_before(now).not_valid_after(now + timedelta(days=365))
                .sign(issuer_key, hashes.SHA256()))
        return {'data': {'id': 'created-123', 'attributes': {
            'certificateType': 'MAC_INSTALLER_DISTRIBUTION',
            'expirationDate': '2027-11-04T00:00:00Z',
            'certificateContent': base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode(),
        }}}


class MacInstallerBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.sut = module()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = self.root / 'runner'
        self.runner.mkdir()
        self.destination = self.root / 'artifacts'
        self.key = PrivateKey.generate()
        self.public_key = base64.b64encode(bytes(self.key.public_key)).decode()

    def run_bootstrap(self, api, create=False, **kwargs):
        return self.sut.bootstrap(api, create=create, public_key=self.public_key,
                                  key_id='github-key-123', runner_temp=self.runner,
                                  output_dir=self.destination, openssl=OPENSSL, **kwargs)

    def test_default_is_read_only_without_encryption_key(self):
        api = FakeAPI(existing=1)
        result = self.sut.bootstrap(api, runner_temp=self.runner, output_dir=self.destination)
        self.assertEqual(result['status'], 'inspect_only')
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(list(self.runner.iterdir()), [])
        self.assertFalse((self.destination / 'sealed-secrets.json').exists())

    def test_only_boolean_true_can_authorize_certificate_creation(self):
        api = FakeAPI()
        for value in ('true', 'false', 1, None):
            with self.assertRaises(ValueError):
                self.run_bootstrap(api, create=value)
        self.assertEqual(api.calls, [])

    def test_existing_certificates_are_reported_without_assuming_team_quota(self):
        api = FakeAPI(existing=2)
        result = self.run_bootstrap(api, create=True)
        self.assertEqual(result['status'], 'created_and_sealed')
        self.assertEqual(len(result['existing_certificates']), 2)
        self.assertEqual([call[0] for call in api.calls], ['GET', 'POST'])
        self.assertEqual(list(self.runner.iterdir()), [])

    def test_missing_or_invalid_github_key_is_rejected_before_apple_write(self):
        api = FakeAPI()
        with self.assertRaises(ValueError):
            self.sut.bootstrap(api, create=True, public_key='invalid', key_id='x',
                               runner_temp=self.runner, output_dir=self.destination)
        self.assertTrue(all(call[0] == 'GET' for call in api.calls))

    def test_empty_runner_temp_never_falls_back_to_workspace_for_private_key(self):
        api = FakeAPI()
        with patch.dict(os.environ, {'RUNNER_TEMP': ''}):
            with self.assertRaisesRegex(ValueError, 'RUNNER_TEMP'):
                self.sut.bootstrap(api, create=True, public_key=self.public_key, key_id='valid-key',
                                   output_dir=self.destination, openssl=OPENSSL)
        self.assertEqual([call[0] for call in api.calls], ['GET'])

    def test_created_p12_is_decryptable_and_artifacts_contain_no_plaintext(self):
        api = FakeAPI()
        out = io.StringIO()
        commands = []
        original_run = subprocess.run

        def record(command, **kwargs):
            commands.append((command, kwargs))
            return original_run(command, **kwargs)

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), patch.object(self.sut.subprocess, 'run', record):
            result = self.run_bootstrap(api, create=True)
        envelope = json.loads((self.destination / 'sealed-secrets.json').read_text(encoding='utf8'))
        self.assertEqual(envelope['target'], 'luolihao-ios/YouTube-News-Player')
        self.assertEqual(envelope['key_id'], 'github-key-123')
        values = {name: SealedBox(self.key).decrypt(base64.b64decode(value)).decode()
                  for name, value in envelope['secrets'].items()}
        self.assertEqual(set(values), {'MAC_INSTALLER_P12_BASE64', 'MAC_INSTALLER_P12_PASSWORD'})
        password = values['MAC_INSTALLER_P12_PASSWORD']
        self.assertGreaterEqual(len(password), 40)
        p12 = base64.b64decode(values['MAC_INSTALLER_P12_BASE64'])
        private, cert, _ = pkcs12.load_key_and_certificates(p12, password.encode())
        self.assertEqual(private.key_size, 2048)
        self.assertEqual(private.public_key().public_numbers(), cert.public_key().public_numbers())
        self.assertEqual(api.csr.public_key().key_size, 2048)
        combined = out.getvalue() + ''.join(path.read_text(encoding='utf8') for path in self.destination.iterdir())
        for value in [password, values['MAC_INSTALLER_P12_BASE64'], 'PRIVATE KEY', 'csrContent']:
            self.assertNotIn(value, combined)
        self.assertEqual(result['status'], 'created_and_sealed')
        self.assertEqual(list(self.runner.iterdir()), [])
        self.assertEqual([call[0] for call in api.calls], ['GET', 'POST'])
        self.assertEqual({p.name for p in self.destination.iterdir()}, {'report.json', 'sealed-secrets.json'})
        for command, options in commands:
            self.assertNotIn(password, ' '.join(command))
            self.assertTrue(options['capture_output'])
            self.assertNotIn('APP_STORE_CONNECT_API_KEY_BASE64', options['env'])

    def test_server_rejection_is_redacted_and_never_retried_or_revoked(self):
        api = FakeAPI(reject=True)
        with self.assertRaisesRegex(RuntimeError, 'Apple.*拒绝') as error:
            self.run_bootstrap(api, create=True)
        self.assertNotIn('PRIVATE-SECRET', str(error.exception))
        self.assertEqual([call[0] for call in api.calls], ['GET', 'POST'])
        self.assertEqual(list(self.runner.iterdir()), [])
        self.assertFalse((self.destination / 'sealed-secrets.json').exists())

    def test_export_failure_preserves_public_id_and_cleans_private_key(self):
        api = FakeAPI()
        original_run = subprocess.run

        def fail_export(command, **kwargs):
            if 'pkcs12' in command:
                raise subprocess.CalledProcessError(1, command, stderr='PRIVATE-SECRET')
            return original_run(command, **kwargs)

        with patch.object(self.sut.subprocess, 'run', fail_export):
            with self.assertRaises(RuntimeError) as error:
                self.run_bootstrap(api, create=True)
        self.assertNotIn('PRIVATE-SECRET', str(error.exception))
        report = json.loads((self.destination / 'report.json').read_text(encoding='utf8'))
        self.assertEqual(report['created_certificate']['id'], 'created-123')
        self.assertEqual(report['status'], 'created_but_not_exported')
        self.assertEqual(list(self.runner.iterdir()), [])
        self.assertEqual([call[0] for call in api.calls], ['GET', 'POST'])

    def test_workflow_existing_secrets_gate_skips_complete_and_blocks_partial_configuration(self):
        workflow = (ROOT / '.github/workflows/macos-signing.yml').read_text(encoding='utf8')
        block = re.search(r'shell: bash\n        run: \|\n((?:          .*\n)+)', workflow)
        self.assertIsNotNone(block, '工作流缺少安装器凭据预检')
        script = '\n'.join(line[10:] for line in block.group(1).splitlines())
        bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')
        for p12, password, expected_code, expected_output in (
            ('PRIVATE-P12', 'PRIVATE-PASSWORD', 0, 'configured=true'),
            ('', '', 0, 'configured=false'),
            ('PRIVATE-P12', '', 1, ''),
            ('', 'PRIVATE-PASSWORD', 1, ''),
        ):
            with self.subTest(has_p12=bool(p12), has_password=bool(password)):
                output = self.root / 'github-output'
                summary = self.root / 'github-summary'
                output.write_text('', encoding='utf8')
                summary.write_text('', encoding='utf8')
                env = {**os.environ, 'EXISTING_INSTALLER_P12': p12,
                       'EXISTING_INSTALLER_PASSWORD': password,
                       'GITHUB_OUTPUT': output.as_posix(), 'GITHUB_STEP_SUMMARY': summary.as_posix()}
                result = subprocess.run([bash, '-c', script], env=env, capture_output=True, text=True, encoding='utf8')
                self.assertEqual(result.returncode, expected_code)
                self.assertEqual(output.read_text(encoding='utf8').strip(), expected_output)
                public_text = result.stdout + result.stderr + summary.read_text(encoding='utf8')
                self.assertNotIn('PRIVATE-P12', public_text)
                self.assertNotIn('PRIVATE-PASSWORD', public_text)


if __name__ == '__main__':
    unittest.main()
