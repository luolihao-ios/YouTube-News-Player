"""用本机 Key 检查真实 API，不输出 Key、请求 URL 或原始错误响应。"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def setting(text, name, default=""):
    values = re.findall(r"^\s*" + re.escape(name) + r"\s*=\s*(.*?)\s*$", text, re.M)
    return values[-1].strip() if values else default

def main():
    parser = argparse.ArgumentParser(description="验证目录身份，默认只查询首页三个频道的直播，以控制配额。")
    parser.add_argument("--live-limit", type=int, default=3)
    args = parser.parse_args()
    seeds = json.loads((ROOT / "NewsLiveApp/Resources/channels.json").read_text(encoding="utf8"))
    if not 0 <= args.live_limit <= len(seeds): parser.error("live-limit 超出目录范围")
    try:
        local = (ROOT / "Config/Local.xcconfig").read_text(encoding="utf-8-sig")
    except OSError:
        print("未找到 Config/Local.xcconfig；请先配置 API Key。", file=sys.stderr)
        return 2
    key = setting(local, "YOUTUBE_API_KEY")
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", key) or key.startswith("YOUR_"):
        print("API Key 未填写或格式不正确；请勿添加引号或其他文字。", file=sys.stderr)
        return 2
    base = (ROOT / "Config/Base.xcconfig").read_text(encoding="utf8")
    bundle = setting(local, "PRODUCT_BUNDLE_IDENTIFIER", setting(base, "PRODUCT_BUNDLE_IDENTIFIER"))

    def get(endpoint, params):
        url = "https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urllib.parse.urlencode({**params, "key": key})
        request = urllib.request.Request(url, headers={"X-Ios-Bundle-Identifier": bundle})
        try:
            with urllib.request.urlopen(request, timeout=25) as response: return json.load(response)
        except urllib.error.HTTPError as error:
            try: payload = json.load(error)
            except (ValueError, OSError): payload = {}
            reasons = [str(item.get("reason", "")).replace(key, "[已隐藏]") for item in payload.get("error", {}).get("errors", [])]
            return {"probe_error": {"http_status": error.code, "reasons": reasons}}
        except Exception as error:
            return {"probe_error": {"network_error_type": type(error).__name__}}

    metadata = get("channels", {"part": "snippet", "id": ",".join(seed["youtubeChannelID"] for seed in seeds), "maxResults": "50"})
    by_id = {item["id"]: item for item in metadata.get("items", [])}
    channels = []
    for seed in seeds:
        item = by_id.get(seed["youtubeChannelID"])
        channels.append({"catalog_id": seed["id"], "name": seed["name"], "channel_id": seed["youtubeChannelID"],
                         "resolved": item is not None, "resolved_title": item["snippet"]["title"] if item else None,
                         "current_handle": item["snippet"].get("customUrl") if item else None})
    live_checks = []
    if not metadata.get("probe_error"):
        for channel in channels[:args.live_limit]:
            if not channel["resolved"]: continue
            search = get("search", {"part": "snippet", "channelId": channel["channel_id"], "type": "video", "eventType": "live",
                                    "videoEmbeddable": "true", "videoSyndicated": "true", "maxResults": "5"})
            ids = [item["id"]["videoId"] for item in search.get("items", []) if item.get("id", {}).get("videoId")]
            result = {"catalog_id": channel["catalog_id"], "search_count": len(ids), "eligible_count": 0, "videos": [], "error": search.get("probe_error")}
            if ids:
                detail = get("videos", {"part": "snippet,status,liveStreamingDetails,contentDetails", "id": ",".join(ids)})
                if detail.get("probe_error"): result["error"] = detail["probe_error"]
                for video in detail.get("items", []):
                    snippet = video.get("snippet", {}); status = video.get("status", {}); stream = video.get("liveStreamingDetails", {})
                    if (status.get("embeddable") is True and status.get("privacyStatus") == "public" and
                            snippet.get("channelId") == channel["channel_id"] and snippet.get("liveBroadcastContent") == "live" and not stream.get("actualEndTime")):
                        result["videos"].append({"id": video["id"], "title": snippet["title"], "concurrent_viewers": stream.get("concurrentViewers"),
                                                 "region_restriction": video.get("contentDetails", {}).get("regionRestriction")})
                result["eligible_count"] = len(result["videos"])
            live_checks.append(result)
            if result["error"]: break
    report = {"checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "bundle_id": bundle,
              "channels": channels, "metadata_error": metadata.get("probe_error"), "live_checks": live_checks,
              "verification_scope": "Windows HTTP API only; not iOS WebKit playback or Xcode build"}
    output = ROOT / ".test-output/youtube-api-check.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["resolved"] for item in channels) and not metadata.get("probe_error") and not any(item["error"] for item in live_checks) else 1

if __name__ == "__main__": sys.exit(main())
