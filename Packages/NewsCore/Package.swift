// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NewsCore",
    platforms: [.iOS(.v17), .macOS(.v14), .visionOS(.v1)],
    products: [.library(name: "NewsCore", targets: ["NewsCore"])],
    targets: [
        .target(name: "NewsCore"),
        .testTarget(name: "NewsCoreTests", dependencies: ["NewsCore"])
    ]
)
