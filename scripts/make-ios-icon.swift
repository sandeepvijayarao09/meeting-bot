// Renders a 1024×1024, fully opaque (no alpha) app icon: a red gradient with a
// white "MB" monogram. App Store icons must be full-bleed and alpha-free; iOS
// applies the rounded-corner mask itself. Usage: swift scripts/make-ios-icon.swift <out.png>
import AppKit
import CoreGraphics
import Foundation
import UniformTypeIdentifiers

let outPath = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "icon-1024.png"
let size = 1024

let colorSpace = CGColorSpaceCreateDeviceRGB()
guard
  let ctx = CGContext(
    data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0,
    space: colorSpace, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
else { fatalError("could not create context") }

// Background: diagonal red gradient (matches the app's record accent).
let colors =
  [
    CGColor(red: 0.87, green: 0.16, blue: 0.16, alpha: 1),
    CGColor(red: 0.52, green: 0.05, blue: 0.09, alpha: 1),
  ] as CFArray
if let gradient = CGGradient(colorsSpace: colorSpace, colors: colors, locations: [0, 1]) {
  ctx.drawLinearGradient(
    gradient, start: CGPoint(x: 0, y: size), end: CGPoint(x: size, y: 0), options: [])
}

// White "MB" monogram, centered.
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: false)
let paragraph = NSMutableParagraphStyle()
paragraph.alignment = .center
let attributes: [NSAttributedString.Key: Any] = [
  .font: NSFont.systemFont(ofSize: 520, weight: .bold),
  .foregroundColor: NSColor.white,
  .paragraphStyle: paragraph,
]
let text = NSAttributedString(string: "MB", attributes: attributes)
let textSize = text.size()
text.draw(
  in: NSRect(
    x: 0, y: (CGFloat(size) - textSize.height) / 2, width: CGFloat(size), height: textSize.height))
NSGraphicsContext.restoreGraphicsState()

guard let image = ctx.makeImage() else { fatalError("could not render image") }
let url = URL(fileURLWithPath: outPath)
guard
  let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)
else { fatalError("could not create destination") }
CGImageDestinationAddImage(dest, image, nil)
if !CGImageDestinationFinalize(dest) { fatalError("could not write \(outPath)") }
print("wrote \(outPath)")
