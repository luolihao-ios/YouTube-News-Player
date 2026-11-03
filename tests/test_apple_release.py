import importlib.util
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

ROOT=Path(__file__).resolve().parents[1]

class ReleaseTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('apple_release',ROOT/'scripts/apple_release.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def test_export_options_include_mac_installer_certificate_only_for_mac(self):
        release=self.load()
        mac=release.export_options('macos','TEAM','profile')
        self.assertEqual(mac['installerSigningCertificate'],'3rd Party Mac Developer Installer')
        self.assertNotIn('installerSigningCertificate',release.export_options('ios','TEAM','profile'))
    def test_profile_rejects_other_bundle_and_other_certificate(self):
        release=self.load()
        valid={'TeamIdentifier':['TEAM'],'UUID':'uuid','Name':'profile','Platform':['OSX'],'ExpirationDate':__import__('datetime').datetime(2099,1,1),
               'DeveloperCertificates':[b'our-cert'],'Entitlements':{'com.apple.application-identifier':'TEAM.com.luolihao.newslive'}}
        release.validate_profile(valid,'macos',b'our-cert')
        with self.assertRaises(ValueError): release.validate_profile(valid,'macos',b'wrong-cert')
        valid['Entitlements']['com.apple.application-identifier']='TEAM.other.app'
        with self.assertRaises(ValueError): release.validate_profile(valid,'macos',b'our-cert')
    def test_artifact_info_requires_name_bundle_and_runtime_config(self):
        release=self.load()
        info={'CFBundleIdentifier':'com.luolihao.newslive','CFBundleVersion':'123','CFBundleShortVersionString':'1.0','CFBundleDisplayName':'YouTubeNewsLive','YouTubeAPIKey':'configured',
              'AppStoreID':'789','ITSAppUsesNonExemptEncryption':False}
        with patch.dict(os.environ,{'BUILD_NUMBER':'123','APP_STORE_ID':'789'}):
            release.validate_info(info,'1.0')
            with self.assertRaises(ValueError): release.validate_info({**info,'CFBundleDisplayName':'NewsLive'},'1.0')
    def test_artifact_version_must_exactly_match_apple_marketing_version(self):
        release=self.load()
        info={'CFBundleIdentifier':'com.luolihao.newslive','CFBundleVersion':'123','CFBundleShortVersionString':'1.0','CFBundleDisplayName':'YouTubeNewsLive','YouTubeAPIKey':'configured','AppStoreID':'789','ITSAppUsesNonExemptEncryption':False}
        with patch.dict(os.environ,{'BUILD_NUMBER':'123','APP_STORE_ID':'789'}):
            release.validate_info(info,'1.0')
            with self.assertRaises(ValueError): release.validate_info({**info,'CFBundleShortVersionString':'1.0.0'},'1.0')
    def test_archive_uses_selected_draft_marketing_version_explicitly(self):
        release=self.load()
        command=release.archive_command('visionos',Path('archive'),'TEAM','profile','Apple Distribution','123','1.0')
        self.assertIn('MARKETING_VERSION=1.0',command)
        self.assertIn('CURRENT_PROJECT_VERSION=123',command)
        self.assertIn('NewsLive-visionOS',command)
    def test_missing_mac_installer_prevents_any_commands(self):
        release=self.load()
        with patch.dict(os.environ,{'IOS_SIGNING_CERTIFICATE_BASE64':'x','IOS_SIGNING_CERTIFICATE_PASSWORD':'x'},clear=True),patch.object(release,'run') as run:
            with self.assertRaisesRegex(ValueError,'MAC_INSTALLER_P12_BASE64'): release.release('macos')
            run.assert_not_called()

    def test_sensitive_failure_keeps_step_and_error_but_redacts_credentials(self):
        release=self.load()
        command=['security','import','signing.p12','-P','local-password']
        error=b'SecKeychainItemImport: MAC verification failed; local-password env-secret'
        completed=subprocess.CompletedProcess(command,51,stdout=b'PRIVATE-STDOUT',stderr=error)
        with patch.dict(os.environ,{'TEST_API_KEY':'env-secret'}),patch.object(release.subprocess,'run',return_value=completed):
            with self.assertRaises(RuntimeError) as raised: release.run(command,sensitive=True)
        message=str(raised.exception)
        self.assertIn('security import',message)
        self.assertIn('51',message)
        self.assertIn('MAC verification failed',message)
        for secret in ('local-password','env-secret','PRIVATE-STDOUT'): self.assertNotIn(secret,message)

    def test_sensitive_failure_removes_private_pem_and_keychain_password(self):
        release=self.load()
        command=['security','set-key-partition-list','-k','temporary-password','keychain']
        error=b'failure temporary-password\n-----BEGIN PRIVATE KEY-----\nsecret-pem\n-----END PRIVATE KEY-----'
        completed=subprocess.CompletedProcess(command,1,stdout=b'',stderr=error)
        with patch.object(release.subprocess,'run',return_value=completed):
            with self.assertRaises(RuntimeError) as raised: release.run(command,sensitive=True)
        self.assertIn('set-key-partition-list',str(raised.exception))
        for secret in ('temporary-password','secret-pem','BEGIN PRIVATE KEY'): self.assertNotIn(secret,str(raised.exception))

    def test_import_container_preserves_private_key_certificate_and_chain(self):
        release=self.load()
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Regression signing identity')])
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(days=1))
              .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1)).sign(key,hashes.SHA256()))
        original=pkcs12.serialize_key_and_certificates(b'original',key,cert,[cert],serialization.BestAvailableEncryption(b'old-password'))
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'original.p12'; source.write_bytes(original)
            target=Path(temporary)/'import.p12'
            password=release.prepare_import_container(source,'old-password',target)
            after_key,after_cert,chain=pkcs12.load_key_and_certificates(target.read_bytes(),password.encode('ascii'))
            self.assertEqual(source.read_bytes(),original)
            self.assertNotEqual(password,'old-password')
            self.assertEqual(after_key.private_numbers(),key.private_numbers())
            self.assertEqual(after_cert.public_bytes(serialization.Encoding.DER),cert.public_bytes(serialization.Encoding.DER))
            self.assertEqual([c.public_bytes(serialization.Encoding.DER) for c in chain],[cert.public_bytes(serialization.Encoding.DER)])
            # DER OIDs: PBE-SHA1-3DES 和 SHA1 MAC；拒绝退回 macOS 无法导入的 PBES2 容器。
            self.assertIn(bytes.fromhex('060a2a864886f70d010c0103'),target.read_bytes())
            self.assertNotIn(bytes.fromhex('06092a864886f70d01050d'),target.read_bytes())

    def test_import_container_rejects_wrong_password_without_writing_output(self):
        release=self.load()
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'source.p12'; source.write_bytes(b'invalid container')
            target=Path(temporary)/'import.p12'
            with self.assertRaises(ValueError) as raised: release.prepare_import_container(source,'hidden-password',target)
            self.assertNotIn('hidden-password',str(raised.exception))
            self.assertFalse(target.exists())

if __name__=='__main__': unittest.main()
