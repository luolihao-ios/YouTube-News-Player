import importlib.util
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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

if __name__=='__main__': unittest.main()
