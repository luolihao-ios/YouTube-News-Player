"""一次性准备 Mac App Store 安装器证书；默认只读，永不撤销旧证书。

创建仅允许显式 --create true。私钥及 P12 仅在 RUNNER_TEMP 的临时目录
短暂存在，最终仅输出 GitHub 仓库公钥加密的 Secrets 和公开证书报告。
Apple 的团队配额以单次签发响应为准，不猜测证书数量上限。
"""
import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from urllib.parse import urlencode

TARGET = 'luolihao-ios/YouTube-News-Player'
CERTIFICATE_TYPE = 'MAC_INSTALLER_DISTRIBUTION'


def public_certificate(item):
    """仅保留可用于人工恢复的公开证书标识和有效期。"""
    return {'id': item['id'], 'expirationDate': item.get('attributes', {}).get('expirationDate')}


def github_box(public_key, key_id):
    """在 Apple 写操作前校验 GitHub 返回的仓库公钥。"""
    from nacl.public import PublicKey, SealedBox
    if not key_id or not public_key:
        raise ValueError('创建前必须提供目标仓库 Secrets 的 public_key 和 key_id')
    try:
        raw = base64.b64decode(public_key, validate=True)
        return SealedBox(PublicKey(raw))
    except (ValueError, TypeError, binascii.Error):
        raise ValueError('GitHub 仓库公钥必须是合法的 32 字节 Base64 公钥') from None


def run_openssl(openssl, arguments, password=None):
    """不向子进程继承 Apple 凭据，不显示可能含敏感信息的进程输出。"""
    environment = {name: os.environ[name] for name in
                   ('PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'HOME') if name in os.environ}
    if password is not None:
        environment['MAC_INSTALLER_EXPORT_PASSWORD'] = password
    try:
        subprocess.run([openssl, *arguments], check=True, capture_output=True,
                       env=environment, timeout=90)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError('OpenSSL 处理失败；已隐藏进程输出，请检查公开证书报告') from None


def write_report(output_dir, report):
    (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')


def bootstrap(api, *, create=False, public_key='', key_id='', runner_temp=None,
              output_dir=None, openssl='openssl'):
    """列出证书，明确授权时仅创建一次；错误路径也会清除临时私钥。"""
    if type(create) is not bool:
        raise ValueError('create 必须是显式布尔值，禁止字符串或数字隐式授权')
    output_dir = Path(output_dir or 'build/mac-installer-bootstrap')
    output_dir.mkdir(parents=True, exist_ok=True)
    # 禁止误用旧密文作为本次成功结果；不自动覆盖既有交付件。
    if (output_dir / 'sealed-secrets.json').exists():
        raise ValueError('输出目录已有密文，请使用新的输出目录，避免覆盖现有签名资料')
    path = 'certificates?' + urlencode({'filter[certificateType]': CERTIFICATE_TYPE, 'limit': '200'})
    try:
        existing = api.all(path)
    except Exception:
        raise RuntimeError('Apple 证书只读查询失败；未执行签发，原始响应已隐藏') from None
    report = {'target': TARGET, 'certificate_type': CERTIFICATE_TYPE,
              'existing_certificates': [public_certificate(item) for item in existing],
              'status': 'inspect_only',
              'message': '仅列出公开证书信息；不会删除、撤销或下载旧证书私钥。'}
    write_report(output_dir, report)
    if not create:
        return report
    box = github_box(public_key, key_id)
    runner_temp_value = runner_temp or os.environ.get('RUNNER_TEMP')
    if not runner_temp_value:
        raise ValueError('创建必须使用存在的 RUNNER_TEMP 目录')
    runner_temp = Path(runner_temp_value)
    if not runner_temp.is_dir():
        raise ValueError('创建必须使用存在的 RUNNER_TEMP 目录')
    try:
        with tempfile.TemporaryDirectory(prefix='mac-installer-', dir=runner_temp) as temporary:
            temporary = Path(temporary)
            temporary.chmod(0o700)
            key, csr = temporary / 'private.pem', temporary / 'request.csr'
            cert_der, cert_pem, p12 = temporary / 'certificate.der', temporary / 'certificate.pem', temporary / 'installer.p12'
            run_openssl(openssl, ['genrsa', '-out', str(key), '2048'])
            key.chmod(0o600)
            run_openssl(openssl, ['req', '-new', '-sha256', '-key', str(key), '-out', str(csr),
                                  '-subj', '/CN=YouTubeNewsLive Mac Installer'])
            try:
                created = api.call('certificates', 'POST', {'data': {'type': 'certificates',
                    'attributes': {'certificateType': CERTIFICATE_TYPE, 'csrContent': csr.read_text(encoding='ascii')}}})['data']
            except Exception:
                report.update(status='apple_rejected_or_unconfirmed',
                              message='Apple 签发被拒绝或响应未确认（可能为配额、权限或网络问题）；未重试、未撤销证书。重跑前请先只读核对证书列表。')
                write_report(output_dir, report)
                raise RuntimeError('Apple 拒绝签发或响应未确认；已停止，未重试或撤销旧证书') from None
            report.update(status='created_but_not_exported', created_certificate=public_certificate(created),
                          message='Apple 已签发；若后续失败，请根据公开 ID 人工检查，避免盲目重复签发。')
            write_report(output_dir, report)
            attrs = created['attributes']
            if attrs.get('certificateType') != CERTIFICATE_TYPE:
                raise RuntimeError('Apple 返回了非安装器证书，停止导出')
            cert_der.write_bytes(base64.b64decode(attrs['certificateContent'], validate=True))
            run_openssl(openssl, ['x509', '-inform', 'DER', '-in', str(cert_der), '-out', str(cert_pem)])
            password = secrets.token_urlsafe(48)
            # 显式使用 macOS security import 兼容的 PKCS#12 算法，避免依赖 legacy provider。
            run_openssl(openssl, ['pkcs12', '-export', '-keypbe', 'PBE-SHA1-3DES',
                                  '-certpbe', 'PBE-SHA1-3DES', '-macalg', 'sha1', '-inkey', str(key), '-in', str(cert_pem),
                                  '-out', str(p12), '-passout', 'env:MAC_INSTALLER_EXPORT_PASSWORD'], password)
            plaintext = {'MAC_INSTALLER_P12_BASE64': base64.b64encode(p12.read_bytes()).decode('ascii'),
                         'MAC_INSTALLER_P12_PASSWORD': password}
            envelope = {'target': TARGET, 'key_id': key_id,
                        'secrets': {name: base64.b64encode(box.encrypt(value.encode('utf8'))).decode('ascii')
                                    for name, value in plaintext.items()}}
            (output_dir / 'sealed-secrets.json').write_text(json.dumps(envelope, indent=2), encoding='utf8')
            report.update(status='created_and_sealed', message='新证书已封装并加密；请将密文写入目标仓库 Secrets 后核对名称。')
            write_report(output_dir, report)
            return report
    except Exception:
        # 本层不打印异常详情，避免第三方库把私钥、P12 或密码带入日志。
        raise RuntimeError('证书准备失败；临时签名文件已清理，请查看公开 report.json；Apple 拒绝时不会重试') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create', choices=('true', 'false'), default='false')
    parser.add_argument('--output-dir', default='build/mac-installer-bootstrap')
    args = parser.parse_args()
    try:
        from appstore import AppleAPI
        report = bootstrap(AppleAPI(), create=args.create == 'true',
                           public_key=os.environ.get('GITHUB_SECRET_PUBLIC_KEY', ''),
                           key_id=os.environ.get('GITHUB_SECRET_KEY_ID', ''),
                           runner_temp=os.environ.get('RUNNER_TEMP'), output_dir=args.output_dir)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception:
        print('Mac 安装器证书准备未完成；详情仅见公开报告，异常原文已隐藏，未自动撤销证书。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
