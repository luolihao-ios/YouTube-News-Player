"""由 GitHub 环境变量生成忽略提交的 xcconfig，不输出凭据。"""
import os
from pathlib import Path
import re

def render(config):
    values = {
        "PRODUCT_BUNDLE_IDENTIFIER": config.get("BUNDLE_ID", "com.luolihao.newslive"),
        "YOUTUBE_API_KEY": config.get("YOUTUBE_API_KEY", ""),
        "APP_STORE_ID": config.get("APP_STORE_ID", ""),
        "PRIVACY_POLICY_URL": config.get("PRIVACY_POLICY_URL", ""),
        "SUPPORT_URL": config.get("SUPPORT_URL", ""),
    }
    lines = ["// 由 CI 生成，不提交版本控制。"]
    for name, value in values.items():
        if any(character in value for character in "\r\n\x00"):
            raise ValueError("CI 配置不能包含换行或空字节: " + name)
        if name == "YOUTUBE_API_KEY" and value and not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("YouTube API Key 格式无效")
        if name.endswith("URL"):
            value = value.replace("https://", "https:/$()/", 1)
        lines.append(f"{name} = {value}")
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "Config/Local.xcconfig"
    destination.write_text(render(os.environ), encoding="utf8")
    print("CI 本机配置已生成，凭据未输出。")
