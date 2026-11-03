"""NewsLive 的 Apple API 身份、签名描述文件、版本及商店资料管理。"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BUNDLE = "com.luolihao.newslive"
LABELS = {
    "en-US": {"name": "NewsLive", "subtitle": "Live news. More perspectives."},
    "zh-Hans": {"name": "NewsLive 新闻直播", "subtitle": "即时新闻，掌握世界每一刻"},
    "zh-Hant": {"name": "NewsLive 新聞直播", "subtitle": "即時新聞，掌握世界每一刻"},
}
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED"}

class AppleAPI:
    def __init__(self):
        import jwt
        names = ["APP_STORE_CONNECT_API_KEY_ID", "APP_STORE_CONNECT_ISSUER_ID", "APP_STORE_CONNECT_API_KEY_BASE64"]
        missing = [name for name in names if not os.environ.get(name)]
        if missing: raise ValueError("缺少仓库 Secret: " + ", ".join(missing))
        key = base64.b64decode(os.environ[names[2]])
        now = int(time.time())
        self.token = jwt.encode({"iss": os.environ[names[1]], "iat": now-10, "exp": now+1100, "aud": "appstoreconnect-v1"}, key,
                                algorithm="ES256", headers={"kid": os.environ[names[0]], "typ": "JWT"})

    def call(self, path, method="GET", data=None):
        if path.startswith("https://api.appstoreconnect.apple.com/"):
            url = path
        elif path.startswith("https:"):
            raise ValueError("拒绝向 Apple 以外的主机发送认证")
        else: url = "https://api.appstoreconnect.apple.com/v1/" + path
        request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                         headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            try: details = json.load(error).get("errors", [])
            except (ValueError, OSError): details = []
            safe = [{"status": item.get("status"), "code": item.get("code"), "detail": item.get("detail")} for item in details]
            raise RuntimeError(f"Apple API HTTP {error.code}: " + json.dumps(safe, ensure_ascii=False)) from None

    def all(self, path):
        items = []
        while path:
            result = self.call(path); items.extend(result.get("data", [])); path = result.get("links", {}).get("next")
        return items

def query(path, **params):
    return path + "?" + urllib.parse.urlencode(params)

def ensure_bundle(api):
    matches = api.call(query("bundleIds", **{"filter[identifier]": BUNDLE, "limit": "10"}))["data"]
    if matches:
        if len(matches) != 1 or matches[0]["attributes"]["identifier"] != BUNDLE:
            raise ValueError("不能唯一确认 NewsLive 的 Bundle ID")
        return matches[0]
    return api.call("bundleIds", "POST", {"data": {"type": "bundleIds", "attributes": {"identifier": BUNDLE, "name": "NewsLive", "platform": "IOS"}}})["data"]

def unique_app(items):
    if not items: return None
    if len(items) != 1 or items[0]["attributes"]["bundleId"] != BUNDLE:
        raise ValueError("不能唯一确认 NewsLive 应用记录，停止操作其他应用")
    return items[0]

def find_app(api):
    return unique_app(api.call(query("apps", **{"filter[bundleId]": BUNDLE, "limit": "10"}))["data"])

def next_build_number(versions, run_number):
    existing = [int(value) for value in versions if str(value).isdigit()]
    return max(int(run_number), max(existing, default=0) + 1)

def output(name, value):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf8") as handle: handle.write(f"{name}={value}\n")

def report(name, data):
    destination = Path("build/apple-report")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / (name + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")

def prepare(api):
    bundle = ensure_bundle(api)
    app = find_app(api)
    result = {"bundle_id": BUNDLE, "apple_bundle_id": bundle["id"], "record_ready": app is not None, "app_id": app["id"] if app else None}
    output("record_ready", "true" if app else "false")
    output("bundle_resource_id", bundle["id"])
    if app:
        output("app_id", app["id"])
        builds = api.all(query("builds", **{"filter[app]": app["id"], "limit": "200"}))
        number = next_build_number([item["attributes"]["version"] for item in builds], os.environ.get("GITHUB_RUN_NUMBER", "1"))
        output("build_number", number); result["next_build"] = number
    else:
        result["required_action"] = "在 App Store Connect 新建 NewsLive，Bundle ID 选择 com.luolihao.newslive，SKU 采用 newslive-ios，主语言采用 English (U.S.)。然后再次运行发布工作流。"
    report("prepare", result)
    print(json.dumps(result, ensure_ascii=False))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf8") as handle:
            handle.write("## NewsLive Apple 准备结果\n\n" + (f"已找到 App Store Connect App `{app['id']}`。" if app else result["required_action"]) + "\n")

def metadata(api):
    app = find_app(api)
    if not app: raise ValueError("尚无 NewsLive App Store 应用记录，请先在网页创建")
    infos = api.all(f"apps/{app['id']}/appInfos?limit=50")
    editable = [item for item in infos if item["attributes"].get("state", item["attributes"].get("appStoreState")) in EDITABLE]
    if len(editable) != 1: raise ValueError("没有唯一可编辑的 NewsLive 商店资料，未改动已发布记录")
    identity = editable[0]["id"]
    path = f"appInfos/{identity}/appInfoLocalizations?limit=50"
    before = {item["attributes"]["locale"]: item for item in api.all(path)}
    for language, labels in LABELS.items():
        if any(not value or len(value) > 30 for value in labels.values()): raise ValueError("名称/副标题超过 Apple 30 字符限制")
        if language in before:
            item_id = before[language]["id"]
            api.call(f"appInfoLocalizations/{item_id}", "PATCH", {"data": {"type": "appInfoLocalizations", "id": item_id, "attributes": labels}})
        else:
            api.call("appInfoLocalizations", "POST", {"data": {"type": "appInfoLocalizations", "attributes": {"locale": language, **labels},
                         "relationships": {"appInfo": {"data": {"type": "appInfos", "id": identity}}}}})
    after = {item["attributes"]["locale"]: item["attributes"] for item in api.all(path)}
    for language, labels in LABELS.items():
        if any(after.get(language, {}).get(key) != value for key, value in labels.items()):
            raise RuntimeError("名称/副标题回读不匹配: " + language)
    report("metadata", LABELS)
    print("已写入并回读 NewsLive 的三语言名称、副标题。")

def provision(api, destination):
    bundle = ensure_bundle(api)
    certificate_path = os.environ["SIGNING_CERTIFICATE_PATH"]
    command = ["openssl", "pkcs12", "-in", certificate_path, "-clcerts", "-nokeys", "-passin", "env:IOS_SIGNING_CERTIFICATE_PASSWORD"]
    cert = subprocess.run(command, capture_output=True)
    if cert.returncode: cert = subprocess.run(command + ["-legacy"], capture_output=True)
    if cert.returncode: raise ValueError("无法从现有 P12 读取签名证书，未输出密码")
    der = subprocess.run(["openssl", "x509", "-outform", "DER"], input=cert.stdout, capture_output=True, check=True).stdout
    digest = hashlib.sha256(der).digest()
    certificates = api.all("certificates?limit=200")
    matches = [item for item in certificates if item["attributes"].get("certificateType") in {"DISTRIBUTION", "IOS_DISTRIBUTION"}
               and hashlib.sha256(base64.b64decode(item["attributes"]["certificateContent"])).digest() == digest]
    if len(matches) != 1: raise ValueError("现有 P12 未对应 Apple 团队的唯一有效发行证书")
    certificate_id = matches[0]["id"]
    profiles = api.all("profiles?filter[profileType]=IOS_APP_STORE&filter[profileState]=ACTIVE&include=bundleId,certificates&limit=200")
    def compatible(profile):
        relationships = profile.get("relationships", {})
        return (relationships.get("bundleId", {}).get("data", {}).get("id") == bundle["id"] and
                any(item["id"] == certificate_id for item in relationships.get("certificates", {}).get("data", [])))
    matching = [item for item in profiles if compatible(item)]
    if matching:
        profile = api.call(f"profiles/{matching[0]['id']}")["data"]
    else:
        name = "NewsLive AppStore " + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        profile = api.call("profiles", "POST", {"data": {"type": "profiles", "attributes": {"name": name, "profileType": "IOS_APP_STORE"},
                    "relationships": {"bundleId": {"data": {"type": "bundleIds", "id": bundle["id"]}},
                                      "certificates": {"data": [{"type": "certificates", "id": certificate_id}]}}}})["data"]
    content = base64.b64decode(profile["attributes"]["profileContent"])
    Path(destination).write_bytes(content)
    print("已准备仅属于 NewsLive 的 App Store 描述文件。")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "metadata", "provision"])
    parser.add_argument("--profile-output", default="")
    args = parser.parse_args(); api = AppleAPI()
    if args.operation == "prepare": prepare(api)
    elif args.operation == "metadata": metadata(api)
    elif args.operation == "provision":
        if not args.profile_output: parser.error("provision 需要 --profile-output")
        provision(api, args.profile_output)

if __name__ == "__main__":
    try: main()
    except Exception as error:
        print("error: " + str(error), file=sys.stderr); sys.exit(1)
