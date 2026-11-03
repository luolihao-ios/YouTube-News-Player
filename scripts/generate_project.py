"""以固定 ID 產生可重現的 Xcode 工程，不依賴 XcodeGen 或第三方套件。"""
from pathlib import Path
import hashlib
import json
import plistlib

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "NewsLive.xcodeproj"

def ident(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()

def quote(value):
    return json.dumps(str(value), ensure_ascii=False)

def generate():
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

if __name__ == "__main__": generate()
