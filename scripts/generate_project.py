"""以固定 ID 产生可重现的三平台 Xcode 工程；使用开发依赖 openstep-parser，不需要 XcodeGen。"""
from pathlib import Path
import hashlib
import json
import plistlib
import copy
import contextlib
import io
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "NewsLive.xcodeproj"

def ident(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()

def quote(value):
    return json.dumps(str(value), ensure_ascii=False)

def generate_base():
    objects = []
    def add(name, value):
        key = ident(name)
        objects.append(f"\t\t{key} = {{ {value} }};")
        return key
    def reference(name): return ident(name)
    def array(values): return "(" + ", ".join(values) + ")"
    source_builds, resource_builds, files = [], [], []
    candidates = sorted((ROOT / "NewsLiveApp").rglob("*.swift"))
    candidates += sorted((ROOT / "NewsLiveApp/Resources").glob("*"))
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix == ".swift": kind = "sourcecode.swift"
        elif path.suffix == ".xcassets": kind = "folder.assetcatalog"
        elif path.suffix == ".html": kind = "text.html"
        elif path.suffix == ".json": kind = "text.json"
        elif path.suffix == ".xcprivacy": kind = "text.xml"
        else: continue
        file_id = add("file:" + relative, f"isa = PBXFileReference; lastKnownFileType = {kind}; path = {quote(relative)}; sourceTree = SOURCE_ROOT;")
        files.append(file_id)
        build_id = add("build:" + relative, f"isa = PBXBuildFile; fileRef = {file_id};")
        (source_builds if path.suffix == ".swift" else resource_builds).append(build_id)
    config_id = add("base-config", 'isa = PBXFileReference; lastKnownFileType = text.xcconfig; path = Config/Base.xcconfig; sourceTree = SOURCE_ROOT;')
    info_id = add("info", 'isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Config/Info.plist; sourceTree = SOURCE_ROOT;')
    product = add("app-product", 'isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = NewsLive.app; sourceTree = BUILT_PRODUCTS_DIR;')
    product_group = add("products", f"isa = PBXGroup; children = {array([product])}; name = Products; sourceTree = \"<group>\";")
    main_group = add("main-group", f"isa = PBXGroup; children = {array(files + [config_id, info_id, product_group])}; sourceTree = \"<group>\";")
    package = add("package", 'isa = XCLocalSwiftPackageReference; relativePath = Packages/NewsCore;')
    dependency = add("package-product", f"isa = XCSwiftPackageProductDependency; package = {package}; productName = NewsCore;")
    framework_build = add("framework-build", f"isa = PBXBuildFile; productRef = {dependency};")
    sources = add("sources", f"isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = {array(source_builds)}; runOnlyForDeploymentPostprocessing = 0;")
    resources = add("resources", f"isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = {array(resource_builds)}; runOnlyForDeploymentPostprocessing = 0;")
    frameworks = add("frameworks", f"isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = {array([framework_build])}; runOnlyForDeploymentPostprocessing = 0;")
    validation = add("release-validation", 'isa = PBXShellScriptBuildPhase; alwaysOutOfDate = 1; buildActionMask = 2147483647; files = (); inputPaths = (); outputPaths = (); name = "驗證發佈設定"; runOnlyForDeploymentPostprocessing = 0; shellPath = /bin/sh; shellScript = ' + quote('if [ "$CONFIGURATION" = "Release" ]; then\n  /usr/bin/python3 "$SRCROOT/scripts/validate_release.py"\nfi\n') + ';')
    project_configs, target_configs = [], []
    for name in ("Debug", "Release"):
        debug = name == "Debug"
        project_configs.append(add("project-" + name, "isa = XCBuildConfiguration; buildSettings = { CLANG_ENABLE_MODULES = YES; CLANG_ENABLE_OBJC_ARC = YES; SDKROOT = iphoneos; IPHONEOS_DEPLOYMENT_TARGET = 17.0; " + ("SWIFT_OPTIMIZATION_LEVEL = \"-Onone\"; DEBUG_INFORMATION_FORMAT = dwarf; ENABLE_TESTABILITY = YES;" if debug else "SWIFT_COMPILATION_MODE = wholemodule; DEBUG_INFORMATION_FORMAT = \"dwarf-with-dsym\";") + f" }}; name = {name};"))
        target_configs.append(add("target-" + name, f"isa = XCBuildConfiguration; baseConfigurationReference = {config_id}; buildSettings = {{ PRODUCT_NAME = NewsLive; SUPPORTED_PLATFORMS = \"iphoneos iphonesimulator\"; SUPPORTS_MACCATALYST = NO; SWIFT_EMIT_LOC_STRINGS = YES; SWIFT_ACTIVE_COMPILATION_CONDITIONS = {quote('DEBUG $(inherited)' if debug else '$(inherited)')}; }}; name = {name};"))
    project_list = add("project-configs", f"isa = XCConfigurationList; buildConfigurations = {array(project_configs)}; defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;")
    target_list = add("target-configs", f"isa = XCConfigurationList; buildConfigurations = {array(target_configs)}; defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;")
    target = add("target", f"isa = PBXNativeTarget; buildConfigurationList = {target_list}; buildPhases = {array([validation,sources,frameworks,resources])}; buildRules = (); dependencies = (); name = NewsLive; packageProductDependencies = {array([dependency])}; productName = NewsLive; productReference = {product}; productType = \"com.apple.product-type.application\";")
    project = add("project", f"isa = PBXProject; attributes = {{ BuildIndependentTargetsInParallel = YES; LastUpgradeCheck = 1620; TargetAttributes = {{ {target} = {{ CreatedOnToolsVersion = 16.2; }}; }}; }}; buildConfigurationList = {project_list}; compatibilityVersion = \"Xcode 14.0\"; developmentRegion = \"zh-Hant\"; hasScannedForEncodings = 0; knownRegions = (\"zh-Hant\", en, Base); mainGroup = {main_group}; packageReferences = {array([package])}; productRefGroup = {product_group}; projectDirPath = \"\"; projectRoot = \"\"; targets = {array([target])};")
    PROJECT.mkdir(exist_ok=True)
    (PROJECT / "project.pbxproj").write_text("// !$*UTF8*$!\n{\n\tarchiveVersion = 1;\n\tclasses = {};\n\tobjectVersion = 56;\n\tobjects = {\n" + "\n".join(objects) + f"\n\t}};\n\trootObject = {project};\n}}\n", encoding="utf-8")
    schemes = PROJECT / "xcshareddata/xcschemes"
    schemes.mkdir(parents=True, exist_ok=True)
    ref = f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="NewsLive.app" BlueprintName="NewsLive" ReferencedContainer="container:NewsLive.xcodeproj"/>'
    (schemes / "NewsLive.xcscheme").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1620" version="1.7">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref}</BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables/></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''', encoding="utf-8")
    workspace = PROJECT / "project.xcworkspace"
    workspace.mkdir(exist_ok=True)
    (workspace / "contents.xcworkspacedata").write_text('<?xml version="1.0" encoding="UTF-8"?><Workspace version="1.0"><FileRef location="self:"/></Workspace>', encoding="utf-8")
    print("已產生 NewsLive.xcodeproj，包含", len(source_builds), "個 Swift 檔案及", len(resource_builds), "項資源。")

def source_paths(platform):
    result = []
    for path in sorted((ROOT / "NewsLiveApp").rglob("*.swift")):
        relative = path.relative_to(ROOT).as_posix()
        if platform == "ios" and "/Desktop/" in relative: continue
        if platform != "ios" and "/Views/" in relative: continue
        result.append(relative)
    return result

def configurations():
    return json.loads((ROOT / "Config/platforms.json").read_text(encoding="utf8"))

def project_graph():
    global PROJECT
    sys.path.insert(0, str(ROOT / ".test-tools"))
    from openstep_parser import OpenStepDecoder
    original = PROJECT
    try:
        with tempfile.TemporaryDirectory(prefix="newslive-project-") as directory:
            PROJECT = Path(directory) / "NewsLive.xcodeproj"
            with contextlib.redirect_stdout(io.StringIO()): generate_base()
            with (PROJECT / "project.pbxproj").open(encoding="utf8") as handle:
                graph = OpenStepDecoder.ParseFromFile(handle)
    finally: PROJECT = original
    objects = graph["objects"]; project = objects[graph["rootObject"]]
    template = copy.deepcopy(objects[ident("target")])
    source_template = copy.deepcopy(objects[ident("sources")])
    file_refs = {obj["path"]: identity for identity,obj in objects.items() if obj.get("isa") == "PBXFileReference" and obj.get("sourceTree") == "SOURCE_ROOT"}
    phases = {identity:copy.deepcopy(objects[identity]) for identity in template["buildPhases"]}
    targets = []
    for platform,details in configurations().items():
        target_id = ident(platform + ":target")
        target = copy.deepcopy(template); target["name"] = details["scheme"]
        target["productName"] = "NewsLive"
        build_phases = []
        for old_id,phase in phases.items():
            phase = copy.deepcopy(phase)
            if phase["isa"] == "PBXSourcesBuildPhase":
                builds = []
                for path in source_paths(platform):
                    build_id = ident(platform + ":source:" + path)
                    objects[build_id] = {"isa":"PBXBuildFile", "fileRef":file_refs[path]}
                    builds.append(build_id)
                phase["files"] = builds
            new_id = ident(platform + ":phase:" + old_id); objects[new_id] = phase; build_phases.append(new_id)
        target["buildPhases"] = build_phases
        target_configs = []
        for mode in ("Debug", "Release"):
            config = copy.deepcopy(objects[ident("target-"+mode)])
            settings = config["buildSettings"]
            settings.update(PRODUCT_BUNDLE_IDENTIFIER="com.luolihao.newslive", SDKROOT=details["sdk"], SUPPORTED_PLATFORMS=details["sdk"] + (" " + details["simulator_sdk"] if "simulator_sdk" in details else ""))
            settings[details["deployment_key"]] = details["minimum"]
            settings["ASSETCATALOG_COMPILER_APPICON_NAME"] = {"ios":"AppIcon", "macos":"AppIconMac", "visionos":"AppIconVision"}[platform]
            settings["INFOPLIST_FILE"] = "Config/Info.plist" if platform == "ios" else "Config/Info-"+details["name"]+".plist"
            settings["TARGETED_DEVICE_FAMILY"] = details.get("family", "")
            if platform == "macos": settings.update(ENABLE_HARDENED_RUNTIME="YES", CODE_SIGN_ENTITLEMENTS="Config/macOS.entitlements", COMBINE_HIDPI_IMAGES="YES")
            config_id = ident(platform + ":config:" + mode); objects[config_id] = config; target_configs.append(config_id)
        config_list_id = ident(platform + ":configs")
        objects[config_list_id] = {"isa":"XCConfigurationList", "buildConfigurations":target_configs,"defaultConfigurationIsVisible":"0","defaultConfigurationName":"Release"}
        target["buildConfigurationList"] = config_list_id
        product_id = ident(platform + ":product")
        product = copy.deepcopy(objects[template["productReference"]]); product["name"] = details["scheme"]+".app"
        objects[product_id] = product; target["productReference"] = product_id
        objects[target_id] = target; targets.append(target_id)
    # 只保留三个实际原生目标，基础模板不作为第四个目标暴露。
    objects.pop(ident("target"), None)
    project["targets"] = targets
    objects[project["productRefGroup"]]["children"] = [objects[target]["productReference"] for target in targets]
    project["attributes"]["TargetAttributes"] = {target:{"CreatedOnToolsVersion":"16.2"} for target in targets}
    for mode in ("Debug", "Release"): objects[ident("project-"+mode)]["buildSettings"].pop("SDKROOT", None)
    return graph

def serialize(value, depth=0):
    if isinstance(value, dict):
        if not value: return "{}"
        return "{\n"+"\n".join("\t"*(depth+1)+serialize(key)+" = "+serialize(item,depth+1)+";" for key,item in value.items())+"\n"+"\t"*depth+"}"
    if isinstance(value, list): return "("+", ".join(serialize(item,depth) for item in value)+")"
    return json.dumps(str(value), ensure_ascii=False)

def generate():
    graph = project_graph()
    PROJECT.mkdir(exist_ok=True)
    (PROJECT / "project.pbxproj").write_text("// !$*UTF8*$!\n"+serialize(graph)+"\n",encoding="utf8")
    # 使用现有共享 Scheme 模板，只替换目标，不引入外部工程依赖。
    with tempfile.TemporaryDirectory(prefix="newslive-schemes-") as directory:
        global_project = globals()["PROJECT"]
        try:
            globals()["PROJECT"] = Path(directory)/"NewsLive.xcodeproj"
            with contextlib.redirect_stdout(io.StringIO()): generate_base()
            template = (globals()["PROJECT"]/"xcshareddata/xcschemes/NewsLive.xcscheme").read_text(encoding="utf8")
        finally: globals()["PROJECT"] = global_project
    schemes = PROJECT/"xcshareddata/xcschemes"; schemes.mkdir(parents=True,exist_ok=True)
    for platform,details in configurations().items():
        scheme = template.replace(ident("target"),ident(platform+":target")).replace('BlueprintName="NewsLive"','BlueprintName="'+details['scheme']+'"')
        (schemes/(details["scheme"]+".xcscheme")).write_text(scheme,encoding="utf8")
    base = plistlib.loads((ROOT/"Config/Info.plist").read_bytes())
    mac = {key:value for key,value in base.items() if not key.startswith("UI") and key not in {"LSRequiresIPhoneOS", "LSSupportsOpeningDocumentsInPlace"}}
    mac.update(LSApplicationCategoryType="public.app-category.news", NSHighResolutionCapable=True, LSMinimumSystemVersion="$(MACOSX_DEPLOYMENT_TARGET)")
    (ROOT/"Config/Info-macOS.plist").write_bytes(plistlib.dumps(mac,sort_keys=False))
    vision = dict(base); vision.pop("LSRequiresIPhoneOS",None); vision.pop("UISupportedInterfaceOrientations",None); vision.pop("UISupportedInterfaceOrientations~ipad",None)
    vision["UIApplicationSceneManifest"] = {"UIApplicationSupportsMultipleScenes":False,"UIApplicationPreferredDefaultSceneSessionRole":"UIWindowSceneSessionRoleApplication"}
    (ROOT/"Config/Info-visionOS.plist").write_bytes(plistlib.dumps(vision,sort_keys=False))
    print("已生成 iOS、macOS、visionOS 三个原生目标。")

if __name__ == "__main__": generate()
