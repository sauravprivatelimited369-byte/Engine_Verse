// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "Meridian",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "MeridianCore", targets: ["MeridianCore"]),
        .executable(name: "Meridian", targets: ["MeridianApp"]),
    ],
    targets: [
        .target(
            name: "MeridianCore",
            path: "Sources/MeridianCore"
        ),
        .executableTarget(
            name: "MeridianApp",
            dependencies: ["MeridianCore"],
            path: "Sources/MeridianApp"
        ),
        .testTarget(
            name: "MeridianCoreTests",
            dependencies: ["MeridianCore"],
            path: "Tests/MeridianCoreTests"
        ),
    ]
)
