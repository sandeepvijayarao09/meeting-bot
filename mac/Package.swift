// swift-tools-version: 5.9
import PackageDescription

let package = Package(
  name: "MeetingBot",
  platforms: [.macOS(.v14), .iOS(.v17)],
  products: [
    // Cross-platform libraries consumed by the macOS app and the iOS app (ios/MB).
    .library(name: "CaptureKit", targets: ["CaptureKit"]),
    .library(name: "MeetingBotKit", targets: ["MeetingBotKit"]),
  ],
  targets: [
    // Audio capture. The mic path (MicCapture/StreamWriter/Manifest) is
    // cross-platform; system-audio capture (ScreenCaptureKit) is macOS-only and
    // #if-guarded, so this compiles for iOS as a mic-only recorder.
    .target(name: "CaptureKit"),
    // Platform-neutral pipeline logic (refine, transcript merge, LLM providers,
    // orchestration). Dependency-free so it builds and unit-tests on any host;
    // the heavy on-device deps (WhisperKit, LiteRT-LM) live in the app targets.
    .target(name: "MeetingBotKit"),
    // macOS-only executables (ScreenCaptureKit + AppKit). Built on the macOS host;
    // an iOS build links only the library products above, not these.
    .executableTarget(
      name: "audiocap",
      dependencies: ["CaptureKit"]),
    .executableTarget(
      name: "MeetingBot",
      dependencies: ["CaptureKit", "MeetingBotKit"]),
    .testTarget(
      name: "MeetingBotKitTests",
      dependencies: ["MeetingBotKit"]),
  ]
)
