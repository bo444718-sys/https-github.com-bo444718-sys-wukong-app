// swift-tools-version: 6.1

import PackageDescription

let package = Package(
    name: "Wukong",
    platforms: [
        .macOS(.v14),
        .iOS(.v17)
    ],
    products: [
        .executable(name: "Wukong", targets: ["Wukong"])
    ],
    targets: [
        .executableTarget(
            name: "Wukong",
            path: "Sources/MichillAppleApp"
        )
    ]
)
