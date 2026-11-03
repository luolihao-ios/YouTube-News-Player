"""在 macOS CI 中分别签名、验证并上传三平台构建；不提交审核或发布。"""
import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('apple_store_release',ROOT/'scripts/appstore.py')
store=importlib.util.module_from_spec(spec); spec.loader.exec_module(store)

def run(command, *, capture=False, sensitive=False):
    result=subprocess.run([str(value) for value in command],capture_output=capture or sensitive)
    if result.returncode:
        if sensitive:
            # 只保留失败步骤、退出码和脱敏 stderr；不输出命令参数或 stdout。
            detail=(result.stderr or b'').decode('utf8',errors='replace')
            hidden=[value for name,value in os.environ.items() if value and any(mark in name.upper() for mark in ('KEY','PASSWORD','SECRET','TOKEN'))]
            hidden += [str(command[index+1]) for index,value in enumerate(command[:-1]) if str(value) in {'-p','-P','-k'}]
            for value in sorted(hidden,key=len,reverse=True): detail=detail.replace(value,'[已隐去]')
            detail=re.sub(r'-----BEGIN [^-]+-----.*?-----END [^-]+-----','[已隐去证书材料]',detail,flags=re.S)
            detail=re.sub(r'[A-Za-z0-9+/=_-]{80,}','[已隐去长编码]',detail)
            step=Path(str(command[0])).name
            if step=='security' and len(command)>1: step+=' '+str(command[1])
            raise RuntimeError(f'签名材料处理失败: {step} (exit {result.returncode})；{detail[-1500:].strip() or "没有错误详情"}')
        raise RuntimeError('命令失败: '+str(command[0])+f' (exit {result.returncode})')
    return result.stdout if capture else None

def prepare_import_container(source, password, destination):
    """保留原密钥、证书及证书链，仅生成 security import 兼容的临时加密容器。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
    source=Path(source); destination=Path(destination)
    if source.resolve()==destination.resolve() or destination.exists():
        raise ValueError('拒绝覆盖现有签名材料')
    try:
        key,certificate,chain=pkcs12.load_key_and_certificates(source.read_bytes(),password.encode('utf8'))
        if key is None or certificate is None: raise ValueError('缺少密钥或证书')
        if key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)!=certificate.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo):
            raise ValueError('密钥与证书不匹配')
    except Exception:
        raise ValueError('现有 P12 未通过完整密钥、证书及密码校验；未更换证书') from None
    temporary_password=secrets.token_urlsafe(36)
    encryption=(serialization.PrivateFormat.PKCS12.encryption_builder().kdf_rounds(50000)
                .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
                .hmac_hash(hashes.SHA1()).build(temporary_password.encode('ascii')))
    encrypted=pkcs12.serialize_key_and_certificates(b'YouTubeNewsLive signing',key,certificate,chain,encryption)
    with destination.open('xb') as output:
        destination.chmod(0o600)
        output.write(encrypted)
    return temporary_password

def export_options(platform,team,profile):
    result={'method':'app-store-connect','signingStyle':'manual','teamID':team,
            'provisioningProfiles':{store.BUNDLE:profile},'uploadSymbols':True,'manageAppVersionAndBuildNumber':False,
            'signingCertificate':'Apple Distribution'}
    if platform=='macos': result['installerSigningCertificate']='3rd Party Mac Developer Installer'
    return result

def validate_profile(profile,platform,certificate):
    teams=profile.get('TeamIdentifier',[])
    entitlements=profile.get('Entitlements',{})
    identity=entitlements.get('application-identifier') or entitlements.get('com.apple.application-identifier')
    expiry=profile.get('ExpirationDate')
    if (len(teams)!=1 or identity!=teams[0]+'.'+store.BUNDLE or
            profile.get('DeveloperCertificates')!=[certificate] or not expiry or
            expiry.replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc)):
        raise ValueError('描述文件身份、证书或有效期不匹配')
    expected='OSX' if platform=='macos' else 'iOS'
    if expected not in profile.get('Platform',[]): raise ValueError('描述文件平台不匹配: '+platform)
    if entitlements.get('get-task-allow') or entitlements.get('com.apple.security.get-task-allow'): raise ValueError('拒绝调试描述文件用于发行')
    return teams[0]

def archive_command(platform, archive, team, profile, identity, build_number, marketing_version):
    config=store.platforms()[platform]
    return ['xcodebuild','archive','-project','NewsLive.xcodeproj','-scheme',config['scheme'],'-configuration','Release',
            '-destination',config['destination'],'-archivePath',archive,'DEVELOPMENT_TEAM='+team,'CODE_SIGN_STYLE=Manual',
            'CODE_SIGN_IDENTITY='+identity,'PROVISIONING_PROFILE_SPECIFIER='+profile,'CURRENT_PROJECT_VERSION='+build_number,
            'MARKETING_VERSION='+marketing_version]

def validate_info(info, marketing_version):
    expected={'CFBundleIdentifier':store.BUNDLE,'CFBundleVersion':os.environ['BUILD_NUMBER'],
              'CFBundleDisplayName':'YouTubeNewsLive','AppStoreID':os.environ['APP_STORE_ID'],'ITSAppUsesNonExemptEncryption':False,
              'CFBundleShortVersionString':marketing_version}
    if any(info.get(key)!=value for key,value in expected.items()): raise ValueError('成品名称、身份、版本或运行配置不匹配')
    key=info.get('YouTubeAPIKey','')
    if not key or '$(' in key: raise ValueError('成品缺少 YouTube 配置')

def release(platform):
    store.require_signing_secrets(platform,os.environ)
    required=['YOUTUBE_API_KEY','APP_STORE_ID','BUILD_NUMBER','APP_STORE_CONNECT_API_KEY_ID','APP_STORE_CONNECT_ISSUER_ID','APP_STORE_CONNECT_API_KEY_BASE64']
    missing=[name for name in required if not os.environ.get(name)]
    if missing: raise ValueError('缺少发布配置: '+', '.join(missing))
    config=store.platforms()[platform]
    temp=Path(os.environ['RUNNER_TEMP'])/('youtubenewslive-'+platform)
    temp.mkdir(parents=True,exist_ok=True)
    destination=ROOT/'build/export'/platform
    destination.mkdir(parents=True,exist_ok=True)
    keychain=temp/'signing.keychain-db'; keychain_password=secrets.token_hex(24)
    original_keychains=[]; installed_profile=None
    key_path=Path.home()/'.appstoreconnect/private_keys'/('AuthKey_'+os.environ['APP_STORE_CONNECT_API_KEY_ID']+'.p8')
    # 防止覆盖登录机器已有同名密钥；GitHub runner 通常不存在此文件。
    if key_path.exists(): raise ValueError('目标 API 密钥文件已存在，拒绝覆盖')
    try:
        run(['xcrun','--sdk',config['sdk'],'--show-sdk-path'])
        run([sys.executable,ROOT/'scripts/configure_ci.py'])
        cert_path=temp/'distribution.p12'
        cert_path.write_bytes(base64.b64decode(os.environ['IOS_SIGNING_CERTIFICATE_BASE64'],validate=True))
        cert_path.chmod(0o600); os.environ['SIGNING_CERTIFICATE_PATH']=str(cert_path)
        api=store.AppleAPI()
        app=store.find_app(api)
        if not app or app['id']!=os.environ['APP_STORE_ID']:
            raise ValueError('发布 App ID 与本 Bundle 实际记录不匹配')
        version=store.select_editable_version(api.all(f"apps/{app['id']}/appStoreVersions?limit=200"),platform)
        marketing_version=version['attributes']['versionString']
        print('本平台 Apple 草稿版本: '+marketing_version)
        cert_der=store.certificate_der(cert_path,'IOS_SIGNING_CERTIFICATE_PASSWORD')
        certificate=store.match_certificate(api,cert_der,store.certificate_types(platform))
        identity='Apple Distribution' if certificate['attributes']['certificateType']=='DISTRIBUTION' else '3rd Party Mac Developer Application' if platform=='macos' else 'iPhone Distribution'
        if platform=='macos':
            installer=temp/'installer.p12'
            installer.write_bytes(base64.b64decode(os.environ['MAC_INSTALLER_P12_BASE64'],validate=True)); installer.chmod(0o600)
            store.match_certificate(api,store.certificate_der(installer,'MAC_INSTALLER_P12_PASSWORD'),{'MAC_INSTALLER_DISTRIBUTION'})
        profile_path=temp/('app.provisionprofile' if platform=='macos' else 'app.mobileprovision')
        store.provision(api,str(profile_path),platform)
        profile=plistlib.loads(run(['security','cms','-D','-i',profile_path],capture=True))
        team=validate_profile(profile,platform,cert_der)
        profile_folder=Path.home()/'Library/MobileDevice/Provisioning Profiles'; profile_folder.mkdir(parents=True,exist_ok=True)
        candidate_profile=profile_folder/(profile['UUID']+profile_path.suffix)
        if candidate_profile.exists(): raise ValueError('目标描述文件已存在，拒绝覆盖')
        shutil.copyfile(profile_path,candidate_profile)
        installed_profile=candidate_profile
        existing=run(['security','list-keychains','-d','user'],capture=True).decode()
        original_keychains=[line.strip().strip('"') for line in existing.splitlines() if line.strip()]
        run(['security','create-keychain','-p',keychain_password,keychain],sensitive=True)
        run(['security','set-keychain-settings','-lut','21600',keychain])
        run(['security','unlock-keychain','-p',keychain_password,keychain],sensitive=True)
        for path,password in [(cert_path,'IOS_SIGNING_CERTIFICATE_PASSWORD')]+([(installer,'MAC_INSTALLER_P12_PASSWORD')] if platform=='macos' else []):
            import_path=path.with_name(path.stem+'-import.p12')
            import_password=prepare_import_container(path,os.environ[password],import_path)
            run(['security','import',import_path,'-k',keychain,'-P',import_password,'-T','/usr/bin/codesign','-T','/usr/bin/productbuild'],sensitive=True)
        run(['security','set-key-partition-list','-S','apple-tool:,apple:,codesign:','-s','-k',keychain_password,keychain],sensitive=True)
        run(['security','list-keychains','-d','user','-s',keychain,*original_keychains])
        archive=temp/'YouTubeNewsLive.xcarchive'
        run(archive_command(platform,archive,team,profile['Name'],identity,os.environ['BUILD_NUMBER'],marketing_version))
        options=export_options(platform,team,profile['Name']); options['signingCertificate']=identity
        options_path=temp/'ExportOptions.plist'; options_path.write_bytes(plistlib.dumps(options))
        run(['xcodebuild','-exportArchive','-archivePath',archive,'-exportPath',destination,'-exportOptionsPlist',options_path])
        extension='pkg' if platform=='macos' else 'ipa'
        artifacts=list(destination.glob('*.'+extension))
        if len(artifacts)!=1: raise ValueError('没有唯一 '+extension+' 成品，停止上传')
        artifact=artifacts[0]
        if platform=='macos':
            apps=list((archive/'Products/Applications').glob('*.app'))
            if len(apps)!=1: raise ValueError('归档不存在唯一 Mac App')
            validate_info(plistlib.loads((apps[0]/'Contents/Info.plist').read_bytes()),marketing_version)
            run(['codesign','--verify','--deep','--strict',apps[0]])
            run(['pkgutil','--check-signature',artifact])
        else:
            with zipfile.ZipFile(artifact) as ipa:
                files=[name for name in ipa.namelist() if name.startswith('Payload/') and name.endswith('.app/Info.plist') and name.count('/')==2]
                if len(files)!=1: raise ValueError('IPA 中没有唯一主 App')
                validate_info(plistlib.loads(ipa.read(files[0])),marketing_version)
        key_path.parent.mkdir(parents=True,exist_ok=True)
        key_path.write_bytes(base64.b64decode(os.environ['APP_STORE_CONNECT_API_KEY_BASE64'],validate=True)); key_path.chmod(0o600)
        # Xcode 从归档平台判断上传类型，避免把 visionOS 当作 iOS 或猜测 altool 平台参数。
        options['destination']='upload'; options_path.write_bytes(plistlib.dumps(options))
        run(['xcodebuild','-exportArchive','-archivePath',archive,'-exportOptionsPlist',options_path,
             '-authenticationKeyPath',key_path,'-authenticationKeyID',os.environ['APP_STORE_CONNECT_API_KEY_ID'],
             '-authenticationKeyIssuerID',os.environ['APP_STORE_CONNECT_ISSUER_ID']])
        store.report('upload-'+platform,{'platform':platform,'build_number':os.environ['BUILD_NUMBER'],'marketing_version':marketing_version,'app_store_version_id':version['id'],'app_id':os.environ['APP_STORE_ID'],
                                       'artifact':str(artifact.relative_to(ROOT)),'upload_command_succeeded':True,'apple_processing_state':'需另行 inspect 回读'})
        print('上传命令成功；Apple 处理状态与 TestFlight 可用性尚待独立回读。')
    finally:
        if original_keychains:
            subprocess.run(['security','list-keychains','-d','user','-s',*original_keychains],capture_output=True)
        subprocess.run(['security','delete-keychain',str(keychain)],capture_output=True)
        key_path.unlink(missing_ok=True)
        if installed_profile and installed_profile.exists(): installed_profile.unlink()
        # temp 为 RUNNER_TEMP 下本任务固定子目录，仅清理本任务签名文件。
        for filename in ['distribution.p12','installer.p12','distribution-import.p12','installer-import.p12','app.mobileprovision','app.provisionprofile']:
            (temp/filename).unlink(missing_ok=True)
        (ROOT/'Config/Local.xcconfig').unlink(missing_ok=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',required=True,choices=['ios','macos','visionos'])
    args=parser.parse_args()
    try: release(args.platform)
    except Exception as error:
        print('error: '+str(error),file=sys.stderr); sys.exit(1)
