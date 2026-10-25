import Foundation
import Vision
import AppKit

// Usage: ocr <image path>
// Prints recognized text lines, one per line, in Vision's reading order.
guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write("usage: ocr <image>\n".data(using: .utf8)!)
    exit(2)
}
let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!)
    exit(3)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("vision error: \(error)\n".data(using: .utf8)!)
    exit(4)
}
for observation in request.results ?? [] {
    if let candidate = observation.topCandidates(1).first {
        print(candidate.string)
    }
}
