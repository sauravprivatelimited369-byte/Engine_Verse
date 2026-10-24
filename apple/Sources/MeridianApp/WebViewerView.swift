import Combine
import MeridianCore
import SwiftUI
import WebKit
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

/// Hardened in-app WKWebView restricted to Meridian's HTTPS origin and base path:
/// - UrlPolicy gates every navigation (external HTTP/HTTPS links open in Safari/browser;
///   javascript:, file:, data:, about: and directory-traversal paths are blocked).
/// - No WKScriptMessageHandler / JavaScript bridge is registered.
/// - Pop-up windows (`javaScriptCanOpenWindowsAutomatically = false`) are refused.
/// - Appends `EngineVerseApple/<version>` so the website can disclose in-app blob limits honestly.
final class WebViewerModel: NSObject, ObservableObject, WKNavigationDelegate, WKUIDelegate {
    @Published var pageTitle: String = AppConfig.appName
    @Published var progress: Double = 0
    @Published var failed: Bool = false
    @Published var canGoBack: Bool = false
    @Published var currentURLString: String

    let startURLString: String
    let policy: UrlPolicy
    fileprivate weak var webView: WKWebView?
    private var observations: [NSKeyValueObservation] = []

    init(path: String, policy: UrlPolicy) {
        self.policy = policy
        let target = policy.pageURL(path)
        self.startURLString = target
        self.currentURLString = target
        super.init()
    }

    func attach(_ view: WKWebView) {
        self.webView = view
        view.navigationDelegate = self
        view.uiDelegate = self
        observations = [
            view.observe(\.estimatedProgress, options: [.new]) { [weak self] wv, _ in
                DispatchQueue.main.async { self?.progress = wv.estimatedProgress }
            },
            view.observe(\.canGoBack, options: [.new]) { [weak self] wv, _ in
                DispatchQueue.main.async { self?.canGoBack = wv.canGoBack }
            },
            view.observe(\.title, options: [.new]) { [weak self] wv, _ in
                guard let raw = wv.title?.trimmingCharacters(in: .whitespacesAndNewlines),
                      !raw.isEmpty,
                      !raw.hasPrefix("http")
                else { return }
                let clean = raw.components(separatedBy: " — ").first?
                    .components(separatedBy: " - ").first ?? raw
                DispatchQueue.main.async { self?.pageTitle = clean }
            },
            view.observe(\.url, options: [.new]) { [weak self] wv, _ in
                guard let abs = wv.url?.absoluteString else { return }
                DispatchQueue.main.async { self?.currentURLString = abs }
            },
        ]
        if let url = URL(string: startURLString) {
            view.load(URLRequest(url: url))
        }
    }

    func goBack() {
        webView?.goBack()
    }

    func reload() {
        failed = false
        if webView?.url != nil {
            webView?.reload()
        } else if let url = URL(string: startURLString) {
            webView?.load(URLRequest(url: url))
        }
    }

    func openCurrentExternally() {
        let target = webView?.url?.absoluteString ?? startURLString
        if policy.decide(target) != .block {
            Self.openExternalURL(target)
        }
    }

    static func makeConfiguredWebView() -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        config.userContentController.removeAllScriptMessageHandlers()
        config.websiteDataStore = .default()
        config.applicationNameForUserAgent = "Safari/605.1.15 EngineVerseApple/\(AppConfig.version)"
        let view = WKWebView(frame: .zero, configuration: config)
        view.allowsBackForwardNavigationGestures = true
        return view
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        let raw = url.absoluteString
        switch policy.decide(raw) {
        case .loadInApp:
            decisionHandler(.allow)
        case .openExternally:
            Self.openExternalURL(raw)
            decisionHandler(.cancel)
        case .block:
            decisionHandler(.cancel)
        }
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let raw = navigationAction.request.url?.absoluteString,
           policy.decide(raw) != .block {
            Self.openExternalURL(raw)
        }
        return nil
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        DispatchQueue.main.async { self.failed = false }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let nsErr = error as NSError
        if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled { return }
        DispatchQueue.main.async { self.failed = true }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let nsErr = error as NSError
        if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled { return }
        DispatchQueue.main.async { self.failed = true }
    }

    private static func openExternalURL(_ raw: String) {
        guard let url = URL(string: raw) else { return }
        #if os(iOS)
        UIApplication.shared.open(url)
        #elseif os(macOS)
        NSWorkspace.shared.open(url)
        #endif
    }
}

#if os(iOS)
private struct PlatformWebView: UIViewRepresentable {
    @ObservedObject var model: WebViewerModel

    func makeUIView(context: Context) -> WKWebView {
        let view = WebViewerModel.makeConfiguredWebView()
        model.attach(view)
        return view
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static func dismantleUIView(_ uiView: WKWebView, coordinator: ()) {
        uiView.stopLoading()
        uiView.navigationDelegate = nil
        uiView.uiDelegate = nil
    }
}
#elseif os(macOS)
private struct PlatformWebView: NSViewRepresentable {
    @ObservedObject var model: WebViewerModel

    func makeNSView(context: Context) -> WKWebView {
        let view = WebViewerModel.makeConfiguredWebView()
        model.attach(view)
        return view
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}

    static func dismantleNSView(_ nsView: WKWebView, coordinator: ()) {
        nsView.stopLoading()
        nsView.navigationDelegate = nil
        nsView.uiDelegate = nil
    }
}
#endif

struct WebViewerSheet: View {
    let path: String
    let policy: UrlPolicy
    let onClose: () -> Void
    let openCatalog: () -> Void

    @StateObject private var model: WebViewerModel
    @Environment(\.colorScheme) private var scheme

    init(path: String, policy: UrlPolicy, onClose: @escaping () -> Void, openCatalog: @escaping () -> Void) {
        self.path = path
        self.policy = policy
        self.onClose = onClose
        self.openCatalog = openCatalog
        _model = StateObject(wrappedValue: WebViewerModel(path: path, policy: policy))
    }

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        NavigationStack {
            ZStack {
                PlatformWebView(model: model)
                VStack(spacing: 0) {
                    if model.progress > 0.01 && model.progress < 0.99 && !model.failed {
                        ProgressView(value: model.progress)
                            .progressViewStyle(.linear)
                    }
                    Spacer()
                }
                if model.failed {
                    VStack(spacing: 12) {
                        Image(systemName: "wifi.slash")
                            .font(.system(size: 40))
                            .foregroundStyle(palette.mutedInk)
                        Text("This page could not load")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(palette.ink)
                        Text("Full notes and the playground need an internet connection. The subject catalogue, your progress and the study planner work offline.")
                            .font(.subheadline)
                            .foregroundStyle(palette.mutedInk)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 420)
                        HStack(spacing: 12) {
                            Button("Try again") {
                                model.reload()
                            }
                            .buttonStyle(.borderedProminent)
                            Button("Open offline catalogue") {
                                openCatalog()
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .padding(32)
                    .background(palette.background)
                }
            }
            .navigationTitle(model.pageTitle)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done", action: onClose)
                }
                ToolbarItemGroup(placement: .automatic) {
                    if model.canGoBack {
                        Button {
                            model.goBack()
                        } label: {
                            Image(systemName: "chevron.left")
                                .accessibilityLabel("Back")
                        }
                    }
                    Button {
                        model.reload()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .accessibilityLabel("Reload")
                    }
                    Button {
                        model.openCurrentExternally()
                    } label: {
                        Image(systemName: "safari")
                            .accessibilityLabel("Open in browser")
                    }
                }
            }
        }
    }
}
