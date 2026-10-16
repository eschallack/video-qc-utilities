// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "URLGuard",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "URLGuard", targets: ["URLGuardApp"]), .library(name: "URLGuardKit", targets: ["URLGuardKit"])],
    targets: [
        .target(name: "URLGuardKit"),
        .executableTarget(name: "URLGuardApp", dependencies: ["URLGuardKit"]),
        .testTarget(name: "URLGuardKitTests", dependencies: ["URLGuardKit"])
    ]
)
