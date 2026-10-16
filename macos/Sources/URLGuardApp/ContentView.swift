import SwiftUI
import UniformTypeIdentifiers
import URLGuardKit

private let yellow = Color(red: 0.96, green: 0.83, blue: 0.27)
private let sidebar = Color(red: 0.10, green: 0.11, blue: 0.13)
private let canvas = Color(red: 0.035, green: 0.04, blue: 0.055)

@MainActor struct ContentView: View {
    @ObservedObject var model: AppModel
    @State private var settingsTab = false
    @State private var collapsed = false
    @State private var targeted = false
    @State private var zoom: Double = 1
    var body: some View {
        HStack(spacing: 0) {
            if !collapsed {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        HStack(spacing: 14) {
                            Image(systemName: "viewfinder").font(.system(size: 38, weight: .bold)).foregroundStyle(yellow)
                            VStack(alignment: .leading, spacing: 2) {
                                HStack { Text("URL Guard").font(.system(size: 27, weight: .bold)); Text("0.2").font(.caption).foregroundStyle(.secondary) }
                                Text("Video Quality Control").foregroundStyle(.secondary)
                            }
                        }.padding(.top, 28)
                        Picker("Panel", selection: $settingsTab) {
                            Text("Redact").tag(false); Text("Settings").tag(true)
                        }.pickerStyle(.segmented).labelsHidden()
                        if settingsTab { advanced } else { workflow }
                        Spacer(minLength: 8)
                        VStack(alignment: .leading, spacing: 5) {
                            Label("Apple Silicon ready", systemImage: "cpu").foregroundStyle(yellow)
                            Text("Vision · Metal · VideoToolbox").font(.caption).foregroundStyle(.secondary)
                            Text("Your media stays on this Mac.").font(.caption).foregroundStyle(.secondary)
                        }
                    }.padding(.horizontal, 24).padding(.bottom, 22)
                }.frame(width: 340).background(sidebar)
            }
            ZStack(alignment: .leading) {
                VStack(spacing: 0) {
                    toolbar
                    ZStack {
                        canvas
                        if model.selected != nil {
                            NativeVideoPreview(player: model.player).scaleEffect(zoom).clipped().padding(24)
                        } else {
                            VStack(spacing: 16) {
                                Image(systemName: "film.stack").font(.system(size: 44, weight: .light)).foregroundStyle(yellow)
                                Text("Select a video").font(.system(size: 25, weight: .bold))
                                Text("Choose a file or drag and drop your videos here.").foregroundStyle(.secondary)
                                Text("MOV · MP4 · M4V").font(.caption).foregroundStyle(.secondary)
                                Button("Choose Video…") { selectVideos(model: model) }.buttonStyle(AccentButton())
                            }.padding(40).background(sidebar.opacity(0.9), in: RoundedRectangle(cornerRadius: 24))
                        }
                    }.overlay { if targeted { RoundedRectangle(cornerRadius: 10).stroke(yellow, lineWidth: 3).padding(12) } }
                    .onDrop(of: [UTType.fileURL], isTargeted: $targeted) { providers in drop(providers) }
                    footer
                }
                Button { withAnimation(.easeInOut(duration: 0.18)) { collapsed.toggle() } } label: {
                    Image(systemName: collapsed ? "chevron.right" : "chevron.left").font(.headline).padding(12)
                }.buttonStyle(.plain).background(sidebar, in: Capsule()).offset(x: -9)
            }
        }.tint(yellow).background(canvas).onChange(of: model.showRender) { _ in model.loadPreview() }
        .onDisappear { model.cancel(); model.stopPlayback() }
    }
    private var workflow: some View {
        VStack(alignment: .leading, spacing: 25) {
            Toggle("Batch processing", isOn: $model.batch).toggleStyle(.switch).disabled(model.busy)
            section("Step 1", "Select video") {
                Button { selectVideos(model: model) } label: { Label("Select Video", systemImage: "video.badge.plus") }
                    .buttonStyle(QuietButton()).disabled(model.busy)
                if let source = model.selected { Text(source.lastPathComponent).font(.caption).lineLimit(2).foregroundStyle(.secondary) }
                if model.batch && model.files.count > 1 {
                    ForEach(model.files, id: \.self) { url in
                        Button(url.lastPathComponent) { model.select(url) }.buttonStyle(.plain).font(.caption)
                            .foregroundStyle(url == model.selected ? yellow : .secondary).disabled(model.busy)
                    }
                }
            }
            section("Step 2", "Mask tracking") {
                Picker("Tracking type", selection: $model.settings.trackingType) {
                    ForEach(TrackingType.allCases) { kind in Text(kind.title).tag(kind) }
                }.labelsHidden().pickerStyle(.segmented).disabled(model.busy)
                Text(model.settings.trackingType.detail).font(.caption).foregroundStyle(.secondary)
                slider("Blur strength", value: $model.settings.blur, range: 1...60, suffix: "px")
                slider("Feather mask", value: $model.settings.feather, range: 0...40, suffix: "px")
                slider("Mask padding", value: $model.settings.padding, range: 0...50, suffix: "px")
            }
            section("Step 3", "Output folder") {
                Text(model.outputFolder?.path ?? "Defaults to the video's folder").font(.caption).foregroundStyle(.secondary).lineLimit(2)
                Button("Set Output Folder") {
                    let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
                    if panel.runModal() == .OK { model.outputFolder = panel.url }
                }.buttonStyle(QuietButton()).disabled(model.busy)
            }
            section("Step 4", "Render") {
                Button { model.start() } label: { Label(model.batch ? "Analyze & Render Batch" : "Analyze & Render", systemImage: "sparkles") }
                    .buttonStyle(AccentButton()).disabled(model.selected == nil || model.busy)
                if model.busy { Button("Cancel") { model.cancel() }.buttonStyle(QuietButton()) }
            }
        }
    }
    private var advanced: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Processing").font(.title3.bold())
            Stepper("OCR every \(model.settings.scanInterval) frames", value: $model.settings.scanInterval, in: 1...120)
            Text("Masks begin at detection. Use 1 for OCR on every frame; higher intervals reduce work and delay visibility confirmation.").font(.caption).foregroundStyle(.secondary)
            Toggle("Detect sideways text", isOn: $model.settings.sideways)
            Toggle("Run black / freeze / audio QC", isOn: $model.settings.runQC)
            Stepper("Tracking threads: \(model.settings.threads)", value: $model.settings.threads, in: 1...16)
            slider("OCR confidence", value: $model.settings.confidence, range: 0.2...1, suffix: "", precision: 2)
            slider("Video bitrate", value: $model.settings.bitrate, range: 2...50, suffix: "Mbps")
            Divider()
            Text("Editable Fusion masks").font(.headline)
            Text("Every render includes corner tracking, Fusion masks, and QC reports. Review coverage before delivery.").foregroundStyle(.secondary)
            Text("8-bit SDR · matching resolution · unretimed source").font(.caption).foregroundStyle(.secondary)
        }.disabled(model.busy)
    }
    private var toolbar: some View {
        HStack {
            Text(model.selected?.lastPathComponent ?? "URL redaction").font(.headline).lineLimit(1)
            Spacer()
            if model.lastOutput != nil {
                Picker("Preview", selection: $model.showRender) { Text("Original").tag(false); Text("Rendered").tag(true) }
                    .pickerStyle(.segmented).frame(width: 190).disabled(model.busy)
            }
            Menu {
                Button("Choose Video…") { selectVideos(model: model) }
                if let folder = model.lastOutput { Button("Open Results") { NSWorkspace.shared.open(folder) } }
                Button("Reset Preview Zoom") { zoom = 1 }
            } label: { Image(systemName: "ellipsis").padding(8) }
            .menuStyle(.borderlessButton).frame(width: 32)
        }.padding(.horizontal, 26).padding(.vertical, 18).background(canvas)
    }
    private var footer: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(model.status).font(.callout.bold()).lineLimit(2)
                    Text(model.detail).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                }
                Spacer()
                if let folder = model.lastOutput {
                    Button("Open Results") { NSWorkspace.shared.open(folder) }.buttonStyle(QuietButton())
                }
                Image(systemName: "minus.magnifyingglass").foregroundStyle(.secondary)
                Slider(value: $zoom, in: 0.5...2).frame(width: 100).disabled(model.selected == nil)
                Image(systemName: "plus.magnifyingglass").foregroundStyle(.secondary)
            }
            ProgressView(value: model.progress).tint(yellow)
        }.padding(24).background(sidebar.opacity(0.55))
    }
    private func section<Content: View>(_ title: String, _ subtitle: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 11) { Text(title).font(.headline); Text(subtitle).foregroundStyle(.secondary); content() }
    }
    private func slider(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, suffix: String, precision: Int = 0) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack { Text(title).font(.callout); Spacer(); Text("\(value.wrappedValue, specifier: precision == 2 ? "%.2f" : "%.0f") \(suffix)").font(.caption.monospacedDigit()).foregroundStyle(.secondary) }
            Slider(value: value, in: range).disabled(model.busy)
        }
    }
    private func drop(_ providers: [NSItemProvider]) -> Bool {
        guard !model.busy else { return false }
        let group = DispatchGroup(); let urls = DroppedURLs()
        for (index, provider) in providers.enumerated() {
            group.enter()
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                var url = item as? URL
                if let data = item as? Data { url = URL(dataRepresentation: data, relativeTo: nil) }
                if let url { urls.append(index: index, url: url) }
                group.leave()
            }
        }
        group.notify(queue: .main) { model.addFiles(urls.snapshot()) }
        return true
    }
}
private final class DroppedURLs: @unchecked Sendable {
    private let lock = NSLock()
    private var entries: [(Int, URL)] = []
    func append(index: Int, url: URL) { lock.lock(); defer { lock.unlock() }; entries.append((index, url)) }
    func snapshot() -> [URL] { lock.lock(); defer { lock.unlock() }; return entries.sorted { $0.0 < $1.0 }.map(\.1) }
}
private struct AccentButton: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.callout.bold()).padding(.horizontal, 20).padding(.vertical, 13)
            .foregroundStyle(.black).background(yellow.opacity(configuration.isPressed ? 0.7 : 1), in: Capsule())
            .opacity(enabled ? 1 : 0.45)
    }
}
private struct QuietButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.callout.weight(.semibold)).padding(.horizontal, 18).padding(.vertical, 12)
            .background(Color.white.opacity(configuration.isPressed ? 0.14 : 0.07), in: Capsule())
    }
}
