"""Release 建置前檢查必需設定；不輸出 API Key。"""
import os
import re
import sys
from urllib.parse import urlparse

def validate(config, for_submission=True):
    errors = []
    def configured(value):
        return bool(value and value.strip() and "$(" not in value and not value.startswith("YOUR_"))
    if not configured(config.get("YOUTUBE_API_KEY", "")):
        errors.append("YOUTUBE_API_KEY 尚未設定。")
    if not re.fullmatch(r"[1-9][0-9]+", config.get("APP_STORE_ID", "")):
        errors.append("APP_STORE_ID 必須是實際 App Store 數字 ID。")
    for name in ("PRIVACY_POLICY_URL", "SUPPORT_URL"):
        value = config.get(name, "")
        if not for_submission and not value:
            continue
        parsed = urlparse(value)
        if not configured(value) or parsed.scheme != "https" or not parsed.hostname:
            errors.append(f"{name} 必須是有效的 HTTPS 網址。")
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", config.get("PRODUCT_BUNDLE_IDENTIFIER", "")):
        errors.append("PRODUCT_BUNDLE_IDENTIFIER 必須是已註冊的 Bundle ID。")
    return errors

if __name__ == "__main__":
    problems = validate(os.environ, for_submission=os.environ.get("RELEASE_STAGE") != "testflight")
    for problem in problems: print(f"error: {problem}", file=sys.stderr)
    if not problems: print("Release 必需設定檢查通過。仍需核對權利、隱私標籤及真機播放。")
    sys.exit(1 if problems else 0)
