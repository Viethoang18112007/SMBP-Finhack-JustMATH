// Receipt reading on the phone with Apple's on-device text recognition (Vision), and the VisionKit
// document camera (automatic crop and straightening). The web app gets back only the lines of text
// and where they are on the page; the picture is never sent anywhere.
//
// JavaScript: window.Capacitor.Plugins.ReceiptScanner
//   scan()               -> the document camera, then { pages: [[line, ...], ...] }
//   recognize({ image }) -> a picture as base64 (JPEG, PNG or HEIC), then { pages: [[line, ...]] }
// A line is { text, confidence, x, y, w, h }: the box from 0 to 1, measured from the top left.
// Errors carry a code: cancelled, camera_denied, unavailable, busy, failed, bad_image.

import AVFoundation
import Capacitor
import UIKit
import Vision
import VisionKit

@objc(ReceiptScannerPlugin)
public class ReceiptScannerPlugin: CAPPlugin, CAPBridgedPlugin, VNDocumentCameraViewControllerDelegate {
    public let identifier = "ReceiptScannerPlugin"
    public let jsName = "ReceiptScanner"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "scan", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "recognize", returnType: CAPPluginReturnPromise)
    ]

    private let maxPages = 3
    private let maxSide: CGFloat = 3000
    private var scanCall: CAPPluginCall?

    @objc func scan(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            if !VNDocumentCameraViewController.isSupported {
                call.reject("The document camera is not available on this device.", "unavailable")
                return
            }
            switch AVCaptureDevice.authorizationStatus(for: .video) {
            case .authorized:
                self.openCamera(call)
            case .notDetermined:
                AVCaptureDevice.requestAccess(for: .video) { granted in
                    DispatchQueue.main.async {
                        if granted {
                            self.openCamera(call)
                        } else {
                            call.reject("Camera access is off.", "camera_denied")
                        }
                    }
                }
            default:
                call.reject("Camera access is off.", "camera_denied")
            }
        }
    }

    @objc func recognize(_ call: CAPPluginCall) {
        let base64 = call.getString("image") ?? ""
        guard let data = Data(base64Encoded: base64), let image = UIImage(data: data) else {
            call.reject("This picture could not be opened.", "bad_image")
            return
        }
        readPages([image], call)
    }

    private func openCamera(_ call: CAPPluginCall) {
        if scanCall != nil {
            call.reject("A scan is already open.", "busy")
            return
        }
        guard let presenter = bridge?.viewController else {
            call.reject("The camera could not open.", "unavailable")
            return
        }
        scanCall = call
        let camera = VNDocumentCameraViewController()
        camera.delegate = self
        presenter.present(camera, animated: true)
    }

    public func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
        var images: [UIImage] = []
        let count = min(scan.pageCount, maxPages)
        for index in 0..<count {
            images.append(scan.imageOfPage(at: index))
        }
        controller.dismiss(animated: true)
        guard let call = scanCall else {
            return
        }
        scanCall = nil
        readPages(images, call)
    }

    public func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
        controller.dismiss(animated: true)
        scanCall?.reject("The scan was cancelled.", "cancelled")
        scanCall = nil
    }

    public func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) {
        controller.dismiss(animated: true)
        scanCall?.reject("The camera failed.", "failed", error)
        scanCall = nil
    }

    // Reading takes a second or two per page: never on the main thread.
    private func readPages(_ images: [UIImage], _ call: CAPPluginCall) {
        DispatchQueue.global(qos: .userInitiated).async {
            var pages: [Any] = []
            for image in images {
                pages.append(self.readLines(image))
            }
            call.resolve(["pages": pages])
        }
    }

    private func readLines(_ image: UIImage) -> [[String: Any]] {
        guard let cgImage = upright(image).cgImage else {
            return []
        }
        let probe = VNRecognizeTextRequest()
        probe.recognitionLevel = .accurate
        let supported = (try? probe.supportedRecognitionLanguages()) ?? []
        let languages = ["en-US", "zh-Hant", "zh-Hans"].filter { supported.contains($0) }
        // If this set of languages is refused, English alone is tried before giving up.
        guard let observations = readText(cgImage, languages) ?? readText(cgImage, ["en-US"]) else {
            return []
        }
        var lines: [[String: Any]] = []
        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else {
                continue
            }
            let box = observation.boundingBox
            lines.append([
                "text": candidate.string,
                "confidence": Double(candidate.confidence),
                "x": Double(box.minX),
                "y": Double(1 - box.maxY),
                "w": Double(box.width),
                "h": Double(box.height)
            ])
        }
        return lines
    }

    private func readText(_ cgImage: CGImage, _ languages: [String]) -> [VNRecognizedTextObservation]? {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        if !languages.isEmpty {
            request.recognitionLanguages = languages
        }
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        do {
            try handler.perform([request])
        } catch {
            return nil
        }
        return request.results ?? []
    }

    // The picture drawn the right way up (a photo's EXIF rotation applied), at most maxSide pixels long.
    private func upright(_ image: UIImage) -> UIImage {
        let longSide = max(image.size.width, image.size.height)
        if longSide <= 0 {
            return image
        }
        let scale = min(1, maxSide / longSide)
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        return renderer.image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}
