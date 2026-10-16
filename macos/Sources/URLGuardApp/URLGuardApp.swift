import SwiftUI
import URLGuardKit

@main @MainActor struct URLGuardApp: App {
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup {
            ContentView(model: model)
                .frame(minWidth: 980, minHeight: 740)
                .preferredColorScheme(.dark)
                .onAppear {
                    let args = CommandLine.arguments
                    if let index = args.firstIndex(of: "--snapshot"), args.count > index + 1 {
                        let path = args[index + 1]
                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                            if let view = NSApplication.shared.windows.first(where: { $0.isVisible })?.contentView,
                               let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
                                view.cacheDisplay(in: view.bounds, to: bitmap)
                                try? bitmap.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
                            }
                            NSApplication.shared.terminate(nil)
                        }
                    } else if model.selected == nil, let source = args.dropFirst().first {
                        model.addFiles([URL(fileURLWithPath: source)])
                    }
                }
                .onOpenURL { model.addFiles([$0]) }
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in model.cancel() }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1200, height: 900)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open Video…") { selectVideos(model: model) }.keyboardShortcut("o")
            }
        }
    }
}

@MainActor func selectVideos(model: AppModel) {
    let panel = NSOpenPanel()
    panel.allowedContentTypes = [.movie, .video]
    panel.allowsMultipleSelection = model.batch
    if panel.runModal() == .OK { model.addFiles(panel.urls) }
}
