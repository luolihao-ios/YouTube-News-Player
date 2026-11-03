"""静态检查；不能代替 Xcode 构建、Swift 类型检查或真机测试。"""
from pathlib import Path
import json
import plistlib
import re
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".test-tools"))
try:
    from tree_sitter import Language, Parser
    import tree_sitter_swift
    from openstep_parser import OpenStepDecoder
except ImportError:
    sys.exit("请先执行 python -m pip install --target .test-tools -r requirements-dev.txt")

def main():
    errors = []
    swift_files = sorted((ROOT / "NewsLiveApp").rglob("*.swift")) + sorted((ROOT / "Packages").rglob("*.swift"))
    swift_files = [p for p in swift_files if ".build" not in p.parts]
    parser = Parser(Language(tree_sitter_swift.language()))
    for path in swift_files:
        data = path.read_bytes()
        tree = parser.parse(data)
        def walk(node):
            if node.type == "ERROR" or node.is_missing:
                errors.append(f"{path.relative_to(ROOT)}:{node.start_point.row + 1}: Swift 语法错误 {node.type}")
            for child in node.children: walk(child)
        walk(tree.root_node)
    with (ROOT / "NewsLive.xcodeproj/project.pbxproj").open(encoding="utf8") as handle:
        project = OpenStepDecoder.ParseFromFile(handle)
    objects = project["objects"]
    targets = [item for item in objects.values() if item.get("isa") == "PBXNativeTarget"]
    if {item["name"] for item in targets} != {"NewsLive", "NewsLive-macOS", "NewsLive-visionOS"}:
        errors.append("工程必须包含且仅包含 iOS、macOS、visionOS 三个原生目标")
    if project["rootObject"] not in objects: errors.append("Xcode rootObject 无效")
    app_files = set()
    for obj in objects.values():
        if obj.get("isa") == "PBXFileReference" and obj.get("sourceTree") == "SOURCE_ROOT":
            path = ROOT / obj["path"]
            if not path.exists(): errors.append(f"Xcode 引用不存在的文件: {obj['path']}")
            app_files.add(obj["path"])
        for key in ("fileRef", "productRef", "baseConfigurationReference", "buildConfigurationList", "mainGroup", "productReference", "productRefGroup", "package"):
            if key in obj and obj[key] not in objects: errors.append(f"Xcode 无效引用 {key}: {obj[key]}")
    for path in (ROOT / "NewsLiveApp").rglob("*.swift"):
        if path.relative_to(ROOT).as_posix() not in app_files: errors.append(f"Swift 文件未加入工程: {path.name}")
    resource_phases = [o for o in objects.values() if o.get("isa") == "PBXResourcesBuildPhase"]
    resource_files = {objects[objects[i]["fileRef"]]["path"] for phase in resource_phases for i in phase["files"]}
    for path in (ROOT / "NewsLiveApp/Resources").iterdir():
        if path.relative_to(ROOT).as_posix() not in resource_files: errors.append(f"资源未打包: {path.name}")
    for path in [ROOT / "Config/Info.plist", ROOT / "Config/Info-macOS.plist", ROOT / "Config/Info-visionOS.plist", ROOT / "Config/macOS.entitlements", ROOT / "NewsLiveApp/Resources/PrivacyInfo.xcprivacy"]:
        with path.open("rb") as handle: plistlib.load(handle)
    for scheme in ("NewsLive", "NewsLive-macOS", "NewsLive-visionOS"):
        ET.parse(ROOT / f"NewsLive.xcodeproj/xcshareddata/xcschemes/{scheme}.xcscheme")
    seeds = json.loads((ROOT / "NewsLiveApp/Resources/channels.json").read_text(encoding="utf8"))
    if len({s["id"].lower() for s in seeds}) != len(seeds): errors.append("频道 handle 重复")
    for seed in seeds:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", seed["id"]): errors.append("频道 handle 无效")
        if seed["category"] not in {"台灣新聞", "國際新聞", "財經", "綜合"}: errors.append("频道分类无效")
    icon = (ROOT / "NewsLiveApp/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png").read_bytes()
    if struct.unpack(">II", icon[16:24]) != (1024,1024) or icon[25] != 2: errors.append("App Icon 必须为1024px不透明RGB PNG")
    if errors:
        for error in errors: print(error)
        return 1
    print(f"静态检查通过：{len(swift_files)} 个 Swift 文件语法、{len(objects)} 个 Xcode 对象、全部资源、{len(seeds)} 个频道、图标及 plist。")
    print("尚未验证 Swift 类型检查、iOS SDK 编译和真机播放。")
    return 0

if __name__ == "__main__": sys.exit(main())
