// swift-tools-version: 5.9
import PackageDescription

let package = Package(
  name: "MeetingBot",
  platforms: [.macOS(.v14)],
  targets: [
    .target(name: "CaptureKit"),
    .executableTarget(
      name: "audiocap",
      dependencies: ["CaptureKit"]),
    .executableTarget(
      name: "MeetingBot",
      dependencies: ["CaptureKit"]),
  ]
)
