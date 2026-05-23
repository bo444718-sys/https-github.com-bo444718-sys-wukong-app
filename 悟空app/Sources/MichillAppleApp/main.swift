import SwiftUI

@main
struct WukongApp: App {
    var body: some Scene {
        WindowGroup {
            DashboardView()
                #if os(macOS)
                .frame(minWidth: 1120, minHeight: 760)
                #endif
        }
        #if os(macOS)
        .windowStyle(.hiddenTitleBar)
        #endif
    }
}

@MainActor
final class DashboardStore: ObservableObject {
    @Published var dashboard: PublicDashboard?
    @Published var report: PublicReportEnvelope?
    @Published var calendar: TradingCalendar?
    @Published var bridge = WukongBridgeStatus()
    @Published var tickerSearch: TickerSearchResult?
    @Published var selectedSection: DashboardSection = .overview
    @Published var selectedTicker: TokenItem?
    @Published var screenMirror: WukongScreenMirror?
    @Published var fileSync: WukongFileSync?
    @Published var searchText = ""
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var watchlist: [String] = []
    @Published var lastRefreshedAt: Date?
    @Published var nextRefreshAt: Date?
    @Published var syncStatus = "等待同步"
    @Published var syncReason = "启动"

    private let api = WukongAPI()
    private let watchlistKey = "wukong.apple.watchlist"
    private let refreshInterval: TimeInterval = 30

    init() {
        watchlist = UserDefaults.standard.stringArray(forKey: watchlistKey) ?? []
    }

    func refresh(reason: String = "定时") async {
        if isLoading { return }
        syncReason = reason
        syncStatus = "同步中"
        isLoading = true
        errorMessage = nil
        do {
            async let dashboardCall = api.fetchDashboard()
            async let reportCall = api.fetchReport()
            async let calendarCall = api.fetchCalendar()
            dashboard = try await dashboardCall
            report = try await reportCall
            calendar = try await calendarCall
            syncLocalBridge(reason: "API同步")
            lastRefreshedAt = Date()
            nextRefreshAt = Date().addingTimeInterval(refreshInterval)
            syncStatus = "实时"
        } catch {
            if applyLocalSnapshot(reason: "快照兜底") {
                errorMessage = nil
                syncStatus = "快照同步"
            } else {
                errorMessage = "无法读取悟空数据：\(error.localizedDescription)"
                syncStatus = "同步失败"
            }
            nextRefreshAt = Date().addingTimeInterval(15)
        }
        isLoading = false
    }

    func startRealtimeUpdates() async {
        await refresh(reason: "启动")
        while !Task.isCancelled {
            nextRefreshAt = Date().addingTimeInterval(refreshInterval)
            do {
                try await Task.sleep(for: .seconds(refreshInterval))
            } catch {
                return
            }
            await refresh(reason: "30秒")
        }
    }

    func refreshIfStale(reason: String) async {
        guard !isLoading else { return }
        let last = lastRefreshedAt ?? .distantPast
        if Date().timeIntervalSince(last) > 10 {
            await refresh(reason: reason)
        }
    }

    func startBridgeSync() async {
        syncLocalBridge(reason: "桥接启动")
        while !Task.isCancelled {
            do {
                try await Task.sleep(for: .seconds(10))
            } catch {
                return
            }
            syncLocalBridge(reason: "桥接同步")
        }
    }

    func syncLocalBridge(reason: String) {
        bridge = api.loadBridgeStatus()
        screenMirror = api.loadScreenMirror() ?? screenMirror
        fileSync = api.loadFileSync() ?? fileSync
        syncReason = reason
    }

    @discardableResult
    func applyLocalSnapshot(reason: String) -> Bool {
        guard let snapshot = api.loadLocalSnapshot() else {
            syncLocalBridge(reason: reason)
            return false
        }
        dashboard = snapshot.dashboard ?? dashboard
        report = snapshot.report ?? report
        calendar = snapshot.calendar ?? calendar
        bridge = api.loadBridgeStatus(snapshot: snapshot)
        screenMirror = api.loadScreenMirror() ?? screenMirror
        fileSync = api.loadFileSync() ?? fileSync
        lastRefreshedAt = Date()
        syncReason = reason
        return true
    }

    func runSearch() async {
        let ticker = searchText.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !ticker.isEmpty else { return }
        isLoading = true
        errorMessage = nil
        do {
            tickerSearch = try await api.searchTicker(ticker)
            selectedSection = .search
        } catch {
            errorMessage = "搜索失败：\(error.localizedDescription)"
        }
        isLoading = false
    }

    func toggleWatch(_ ticker: String) {
        let normalized = ticker.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !normalized.isEmpty else { return }
        if watchlist.contains(normalized) {
            watchlist.removeAll { $0 == normalized }
        } else {
            watchlist.insert(normalized, at: 0)
        }
        UserDefaults.standard.set(watchlist, forKey: watchlistKey)
    }

    func isWatched(_ ticker: String) -> Bool {
        watchlist.contains(ticker.uppercased())
    }

    var watchedItems: [TokenItem] {
        let all = dashboard?.allTokens ?? []
        return watchlist.compactMap { ticker in all.first { $0.ticker == ticker } }
    }
}

struct DashboardView: View {
    @StateObject private var store = DashboardStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        NavigationSplitView {
            Sidebar(store: store)
        } detail: {
            ZStack {
                AppBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        HeroHeader(store: store)
                        StatusStrip(store: store)
                        SkillCenterView(store: store)
                        ScreenMirrorSummary(store: store)
                        Disclaimer()
                        SectionContent(store: store)
                    }
                    .padding(24)
                }
            }
            .sheet(item: $store.selectedTicker) { token in
                TokenDetailView(token: token, store: store)
                    .frame(minWidth: 560, minHeight: 680)
            }
            .task {
                await store.startRealtimeUpdates()
            }
            .task {
                await store.startBridgeSync()
            }
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .active {
                    Task { await store.refreshIfStale(reason: "回到前台") }
                }
            }
            .refreshable {
                await store.refresh(reason: "手动下拉")
            }
        }
    }
}

struct Sidebar: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        List(selection: $store.selectedSection) {
            Section("研究台") {
                ForEach(DashboardSection.primary) { section in
                    Label(section.title, systemImage: section.icon).tag(section)
                }
            }
            Section("个人") {
                Label("我的关注", systemImage: "star.fill").tag(DashboardSection.watchlist)
                Label("币种搜索", systemImage: "magnifyingglass").tag(DashboardSection.search)
                Label("悟空技能", systemImage: "wand.and.stars").tag(DashboardSection.skills)
                Label("图片同步", systemImage: "photo.on.rectangle.angled").tag(DashboardSection.mirror)
                Label("文件同步", systemImage: "folder.badge.gearshape").tag(DashboardSection.files)
            }
            if let sections = store.dashboard?.sections, !sections.isEmpty {
                Section("公开接口") {
                    ForEach(sections.prefix(10)) { section in
                        HStack {
                            Text(section.label)
                            Spacer()
                            Text("\(section.count)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("悟空")
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 8) {
                Button {
                    Task { await store.refresh(reason: "手动刷新") }
                } label: {
                    Label(store.isLoading ? "刷新中" : "刷新数据", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isLoading)

                if let generatedAt = store.dashboard?.generatedAt {
                    Text("生成 \(DateFormatter.short.string(from: generatedAt))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let lastRefreshedAt = store.lastRefreshedAt {
                    Text("App刷新 \(DateFormatter.short.string(from: lastRefreshedAt))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding()
        }
    }
}

struct HeroHeader: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("WUKONG · Binance 合约研究台")
                        .font(.caption.weight(.heavy))
                        .foregroundStyle(.cyan)
                    Text("悟空")
                        .font(.system(size: 42, weight: .black, design: .rounded))
                    Text("用 Binance 合约 OI、资金费率、成交量、价格位置和 DEX/社媒扩散，寻找可能提前启动的高波动机会。只做信号和复盘，不替你负责下单。")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                if let calendar = store.calendar {
                    CalendarSummary(calendar: calendar)
                }
            }
            TickerTape()
        }
        .padding(24)
        .glassCard(radius: 28)
    }
}

struct StatusStrip: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
                StatusChip(title: "行情生成", value: freshness(now: context.date))
                StatusChip(title: "同步状态", value: store.isLoading ? "同步中" : store.syncStatus)
                StatusChip(title: "下次刷新", value: countdown(now: context.date))
                StatusChip(title: "触发来源", value: store.syncReason)
            }
        }
    }

    private func freshness(now: Date) -> String {
        guard let date = store.dashboard?.generatedAt else { return "等待生成" }
        let minutes = max(0, Int(now.timeIntervalSince(date) / 60))
        if minutes <= 1 { return "刚刚生成" }
        if minutes < 60 { return "\(minutes) 分钟前" }
        return DateFormatter.short.string(from: date)
    }

    private func countdown(now: Date) -> String {
        guard let next = store.nextRefreshAt else { return "30秒" }
        let seconds = max(0, Int(next.timeIntervalSince(now)))
        if seconds == 0 { return store.isLoading ? "同步中" : "即将同步" }
        return "\(seconds)秒"
    }
}

struct SkillCenterView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
            SkillChip(title: "实时同步", value: "30秒 + 前台恢复", icon: "arrow.triangle.2.circlepath")
            SkillChip(title: "机会扫描", value: "\(store.dashboard?.frontPageTokens.count ?? 0) 个候选", icon: "scope")
            SkillChip(title: "风险过滤", value: "\(store.dashboard?.riskCount ?? 0) 个风险样本", icon: "exclamationmark.shield")
            SkillChip(title: "快照同步", value: store.bridge.snapshotText, icon: "externaldrive.connected.to.line.below")
            SkillChip(title: "iPhone链接", value: store.bridge.installText, icon: "iphone")
            SkillChip(title: "Telegram联动", value: store.bridge.telegramText, icon: "paperplane.fill")
            SkillChip(title: "文件同步", value: "\(store.fileSync?.fileCount ?? 0) 个文件", icon: "folder.badge.gearshape")
        }
    }
}

struct SkillChip: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.headline)
                .foregroundStyle(.cyan)
                .frame(width: 28, height: 28)
                .background(.cyan.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.callout.weight(.heavy))
                Text(value)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .glassCard(radius: 18)
    }
}

struct ScreenMirrorSummary: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        if let mirror = store.screenMirror {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: "photo.on.rectangle.angled")
                    .font(.title3)
                    .foregroundStyle(.cyan)
                VStack(alignment: .leading, spacing: 6) {
                    Text("图片内容已同步到悟空 App")
                        .font(.headline)
                    Text("\(mirror.title) · \(mirror.priorityRead?.title ?? "今日优先扫读") \(mirror.priorityRead?.count ?? "--") · \(mirror.updatedText)")
                        .foregroundStyle(.secondary)
                    if let installURL = store.bridge.installURL.nilIfEmpty {
                        Text("iPhone 链接：\(installURL)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer()
                Button {
                    store.selectedSection = .mirror
                } label: {
                    Label("查看", systemImage: "arrow.right.circle")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(16)
            .glassCard(radius: 20)
        }
    }
}

struct Disclaimer: View {
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text("公开测试提醒")
                .fontWeight(.heavy)
                .foregroundStyle(.cyan)
            Text("这里只做早期资金结构、链上/社媒扩散和合约数据观察，不构成投资建议。数据可能延迟、缺失或误判，合约波动很大，请自己控制仓位和止损。")
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .glassCard(radius: 20)
    }
}

struct SectionContent: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        switch store.selectedSection {
        case .overview:
            OverviewView(store: store)
        case .review:
            ReviewView(report: store.report)
        case .entry:
            TokenSectionView(title: "入场窗口", subtitle: "从公开早发现里再收窄一层，只保留价格还不晚、OI/量能/费率干净、且不是场所单独触发的币。", items: store.dashboard?.entryWindow ?? [], store: store)
        case .early:
            TokenSectionView(title: "早发现雷达", subtitle: "把 OI、价格位置、资金费率、量能、社媒热度和多场所共振压成一张综合信号卡。", items: store.dashboard?.earlyEntryRadar ?? [], store: store)
        case .opportunities:
            TokenSectionView(title: "确认/回踩候选", subtitle: "已经启动或需要二次确认的币，重点看是否等回踩、是否仍有 OI/成交接力。", items: store.dashboard?.opportunities ?? [], store: store, showFilters: true)
        case .signals:
            SignalChangesView(items: store.dashboard?.recentSignalChanges ?? [], store: store)
        case .radar:
            RadarView(store: store)
        case .breakout:
            TokenSectionView(title: "已启动复盘", subtitle: "之前出现过、现在已经大幅启动的币，主要用于复盘和等回踩，不直接追高。", items: store.dashboard?.breakoutReview ?? [], store: store)
        case .risk:
            RiskView(store: store)
        case .watchlist:
            WatchlistView(store: store)
        case .search:
            SearchView(store: store)
        case .skills:
            SkillsView(store: store)
        case .mirror:
            ScreenMirrorView(store: store)
        case .files:
            FileSyncView(store: store)
        }
    }
}

struct FileSyncView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "悟空文件同步", subtitle: "自动读取悟空目录核心文件，展示路径、角色、大小、哈希和文本预览；网页下载端也读取同一份清单。", count: store.fileSync?.fileCount ?? 0)
            if let sync = store.fileSync {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 10)], spacing: 10) {
                    ForEach(sync.roleItems) { item in
                        MiniMetric(title: item.title, value: "\(item.count)")
                    }
                }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 12)], spacing: 12) {
                    ForEach(sync.files.prefix(36)) { file in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(file.path)
                                    .font(.headline)
                                    .lineLimit(1)
                                Spacer()
                                Text(file.role)
                                    .font(.caption.weight(.heavy))
                                    .foregroundStyle(.cyan)
                            }
                            Text("\(file.sizeText) · \(file.modifiedText)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(file.sha256.prefix(12) + "…")
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                            if !file.preview.isEmpty {
                                Text(file.preview)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(5)
                            }
                        }
                        .padding(14)
                        .background(.white.opacity(0.46), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    }
                }
            } else {
                EmptyState(text: "等待文件同步清单。")
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct ScreenMirrorView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "图片同步镜像", subtitle: "来自用户提供截图的所有可见内容；App 会继续用实时 API 和 Hermes 快照自动更新。", count: store.screenMirror?.overviewCards.count ?? 0)
            if let mirror = store.screenMirror {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(mirror.subtitle)
                                .font(.caption.weight(.heavy))
                                .foregroundStyle(.cyan)
                            Text(mirror.title)
                                .font(.system(size: 40, weight: .black, design: .rounded))
                            Text(mirror.description)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if let calendar = mirror.calendar {
                            VStack(alignment: .trailing, spacing: 6) {
                                Text(calendar.label)
                                    .font(.caption.weight(.heavy))
                                    .foregroundStyle(.secondary)
                                Text(calendar.returnText)
                                    .font(.system(size: 30, weight: .black, design: .rounded))
                                    .foregroundStyle(.green)
                                Text(calendar.detail)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(14)
                            .background(.white.opacity(0.48), in: RoundedRectangle(cornerRadius: 16))
                        }
                    }
                    TickerMirror(tags: mirror.tags)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], spacing: 10) {
                        ForEach(mirror.status) { item in
                            MiniMetric(title: item.title, value: item.value)
                        }
                    }
                    Text(mirror.notice)
                        .font(.callout)
                        .foregroundStyle(.orange)
                        .padding(12)
                        .background(.white.opacity(0.42), in: RoundedRectangle(cornerRadius: 14))
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
                        ForEach(mirror.overviewCards) { card in
                            SkillDetailCard(title: card.title, detail: card.note, value: card.value)
                        }
                    }
                    if let priority = mirror.priorityRead {
                        SkillDetailCard(title: priority.title, detail: priority.description, value: priority.count)
                    }
                    SidebarMirror(sidebar: mirror.sidebar)
                }
            } else {
                EmptyState(text: "还没有读取到图片同步镜像。")
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct TickerMirror: View {
    let tags: [String]

    var body: some View {
        HStack(spacing: 8) {
            ForEach(tags, id: \.self) { tag in
                Text(tag)
                    .font(.caption.bold())
                    .foregroundStyle(.cyan)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.white.opacity(0.55), in: Capsule())
            }
        }
    }
}

struct SidebarMirror: View {
    let sidebar: WukongMirrorSidebar?

    var body: some View {
        if let sidebar {
            VStack(alignment: .leading, spacing: 10) {
                Text("侧栏公开接口")
                    .font(.headline)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 8)], spacing: 8) {
                    ForEach(sidebar.publicSections) { item in
                        MiniMetric(title: item.title, value: item.value)
                    }
                }
            }
        }
    }
}

struct SkillsView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "悟空技能", subtitle: "把实时同步、机会扫描、风险过滤、Telegram 联动和本机关注整理成可检查的能力面板。", count: 6)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                SkillDetailCard(title: "实时同步", detail: "启动立即同步，每 30 秒刷新；App 回到前台会主动补一次，手动下拉也会触发。", value: store.syncStatus)
                SkillDetailCard(title: "机会扫描", detail: "整合入场窗口、早发现雷达、确认/回踩候选、OI 异动和合约异动。", value: "\(store.dashboard?.frontPageTokens.count ?? 0) 条")
                SkillDetailCard(title: "风险过滤", detail: "集中展示公告风险、过热回避和退市/低置信样本。", value: "\(store.dashboard?.riskCount ?? 0) 条")
                SkillDetailCard(title: "本地快照", detail: "自动读取 Hermes 运行目录的最新快照；公开 API 失败时会用快照兜底。", value: store.bridge.snapshotText)
                SkillDetailCard(title: "iPhone 安装", detail: "自动读取 PWA 当前 HTTPS 链接，Telegram 摘要和 App 能保持同一个入口。", value: store.bridge.installText)
                SkillDetailCard(title: "Telegram 联动", detail: "实时摘要、iPhone 安装链接和最新快照会同步到现有机器人。", value: store.bridge.telegramText)
                SkillDetailCard(title: "文件同步", detail: "扫描悟空目录全部核心文件，生成哈希、大小、修改时间和文本预览，同步到 App 与网页下载端。", value: "\(store.fileSync?.fileCount ?? 0) 个")
                SkillDetailCard(title: "本机关注", detail: "关注列表保存在本机，刷新后继续匹配公开摘要中的完整卡片。", value: "\(store.watchlist.count) 个")
                SkillDetailCard(title: "搜索轨迹", detail: "按币种查询公开池子出现历史、信号来源和后续状态。", value: store.tickerSearch?.ticker ?? "待搜索")
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct SkillDetailCard: View {
    let title: String
    let detail: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title)
                    .font(.headline)
                Spacer()
                Text(value)
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(.cyan)
                    .lineLimit(1)
            }
            Text(detail)
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.white.opacity(0.48), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

struct OverviewView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let error = store.errorMessage {
                Text(error)
                    .foregroundStyle(.red)
                    .padding()
                    .glassCard(radius: 18)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
                OverviewCard(title: "入场窗口", value: store.dashboard?.counts.entryWindow ?? 0, note: "更接近可盯入场", tone: .good) { store.selectedSection = .entry }
                OverviewCard(title: "早发现雷达", value: store.dashboard?.counts.earlyEntryRadar ?? 0, note: "更早提示，不等于买点", tone: .good) { store.selectedSection = .early }
                OverviewCard(title: "确认/回踩候选", value: store.dashboard?.opportunities.count ?? 0, note: "已启动或等二次确认", tone: .warm) { store.selectedSection = .opportunities }
                OverviewCard(title: "信号切换", value: store.dashboard?.counts.recentSignalChanges ?? 0, note: "刚触发/刚退役会保留", tone: .hot) { store.selectedSection = .signals }
                OverviewCard(title: "多次出现", value: store.dashboard?.counts.repeatCandidateWatch ?? 0, note: "反复被扫到，先复核", tone: .warm) { store.selectedSection = .radar }
                OverviewCard(title: "OI异动", value: store.dashboard?.counts.oiAnomalyWatch ?? 0, note: "价格未放完但 OI 已动", tone: .good) { store.selectedSection = .radar }
                OverviewCard(title: "风险区", value: store.dashboard?.riskCount ?? 0, note: "过热/公告/回避", tone: .hot) { store.selectedSection = .risk }
                OverviewCard(title: "我的关注", value: store.watchlist.count, note: "手动加入的币不会丢", tone: .good) { store.selectedSection = .watchlist }
            }

            TokenSectionView(title: "今日优先扫读", subtitle: "把入场窗口、早发现雷达和确认候选合并做一层首页摘要。", items: Array(store.dashboard?.frontPageTokens.prefix(18) ?? []), store: store)
        }
    }
}

struct TokenSectionView: View {
    let title: String
    let subtitle: String
    let items: [TokenItem]
    @ObservedObject var store: DashboardStore
    var showFilters = false
    @State private var stage = "全部"

    private var filtered: [TokenItem] {
        guard showFilters, stage != "全部" else { return items }
        return items.filter { $0.currentStage == stage || $0.stage == stage }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionHeader(title: title, subtitle: subtitle, count: filtered.count)
            if showFilters {
                Picker("状态", selection: $stage) {
                    ForEach(["全部", "候选观察", "小仓试错", "可追", "等待回踩", "回避"], id: \.self) { Text($0) }
                }
                .pickerStyle(.segmented)
            }
            if filtered.isEmpty {
                EmptyState()
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], spacing: 14) {
                    ForEach(filtered) { token in
                        TokenCard(token: token, isWatched: store.isWatched(token.ticker)) {
                            store.toggleWatch(token.ticker)
                        } open: {
                            store.selectedTicker = token
                        }
                    }
                }
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct ReviewView: View {
    let report: PublicReportEnvelope?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "AI复盘", subtitle: "公开展示今日观察结论、信号共性、风险提醒和数据边界。", count: report?.counts?.appearedToday ?? 0)

            if let publicReport = report?.publicReport {
                VStack(alignment: .leading, spacing: 14) {
                    Text(publicReport.headline ?? "等待复盘")
                        .font(.title2.bold())
                    Text(publicReport.analysis ?? publicReport.aiConclusion ?? "")
                        .foregroundStyle(.secondary)
                        .lineSpacing(4)
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 4), spacing: 10) {
                        MetricTile(title: "进入视野", value: "\(report?.counts?.appearedToday ?? 0)")
                        MetricTile(title: "可复盘", value: "\(report?.counts?.trustedReturns ?? 0)")
                        MetricTile(title: "涨超10%", value: "\(report?.counts?.hit10 ?? 0)")
                        MetricTile(title: "涨超30%", value: "\(report?.counts?.hit30 ?? 0)")
                    }
                    if let highlights = publicReport.aiPublicHighlights {
                        ForEach(highlights, id: \.self) { item in
                            Label(item, systemImage: "sparkles")
                                .foregroundStyle(.secondary)
                        }
                    }
                    FeatureStatsGrid(stats: publicReport.featureStats ?? [])
                    ComboGrid(combos: publicReport.featureCombos ?? [])
                    Text(publicReport.riskNote ?? publicReport.dataNote ?? "")
                        .font(.callout)
                        .foregroundStyle(.orange)
                }
            } else {
                EmptyState(text: "还没有读取到 AI 复盘。")
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct RadarView: View {
    @ObservedObject var store: DashboardStore
    @State private var tab: RadarTab = .oi

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionHeader(title: "机会雷达", subtitle: "把 OI、蓄势、DEX、合约、市场确认和回避合并成一个切换区。", count: currentItems.count)
            Picker("雷达", selection: $tab) {
                ForEach(RadarTab.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], spacing: 14) {
                ForEach(currentItems) { token in
                    TokenCard(token: token, isWatched: store.isWatched(token.ticker)) {
                        store.toggleWatch(token.ticker)
                    } open: {
                        store.selectedTicker = token
                    }
                }
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }

    private var currentItems: [TokenItem] {
        guard let dashboard = store.dashboard else { return [] }
        switch tab {
        case .oi: return dashboard.oiAnomalyWatch
        case .repeatPool: return dashboard.repeatCandidateWatch
        case .accumulation: return dashboard.accumulationWatch
        case .market: return dashboard.marketWatch
        case .futures: return Array(dashboard.futuresMovers.prefix(40))
        }
    }
}

struct SignalChangesView: View {
    let items: [TokenItem]
    @ObservedObject var store: DashboardStore

    var body: some View {
        TokenSectionView(title: "信号轨迹", subtitle: "刚触发或刚退役的信号会留在这里，不让状态变化静默消失。", items: items, store: store)
    }
}

struct RiskView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            TokenSectionView(title: "公告风险", subtitle: "退市、公告或低置信风险集中在这里。", items: store.dashboard?.delistRiskWatch ?? [], store: store)
            TokenSectionView(title: "过热回避", subtitle: "价格、OI、成交或社媒已经偏热，不追第一波。", items: store.dashboard?.overheated ?? [], store: store)
        }
    }
}

struct WatchlistView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionHeader(title: "我的关注", subtitle: "保存在本机 UserDefaults，不写回服务器。", count: store.watchlist.count)
            if store.watchlist.isEmpty {
                EmptyState(text: "还没有关注币。打开任意卡片右上角的星标即可加入。")
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], spacing: 14) {
                    ForEach(store.watchlist, id: \.self) { ticker in
                        if let token = store.watchedItems.first(where: { $0.ticker == ticker }) {
                            TokenCard(token: token, isWatched: true) {
                                store.toggleWatch(ticker)
                            } open: {
                                store.selectedTicker = token
                            }
                        } else {
                            WatchTickerCard(ticker: ticker) {
                                store.searchText = ticker
                                Task { await store.runSearch() }
                            } remove: {
                                store.toggleWatch(ticker)
                            }
                        }
                    }
                }
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct SearchView: View {
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionHeader(title: "币种搜索", subtitle: "查一个币是否进过池子、什么时候出现、当时信号和后续涨幅。", count: store.tickerSearch?.appearances.count ?? 0)
            HStack {
                TextField("输入币种，例如 ORCA / BAS / SPK", text: $store.searchText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await store.runSearch() } }
                Button {
                    Task { await store.runSearch() }
                } label: {
                    Label("搜索轨迹", systemImage: "magnifyingglass")
                }
                .buttonStyle(.borderedProminent)
            }
            if let result = store.tickerSearch {
                if result.found {
                    SearchResultView(result: result, store: store)
                } else {
                    EmptyState(text: "\(result.ticker) 暂未在公开池子里出现。")
                }
            }
        }
        .padding(20)
        .glassCard(radius: 26)
    }
}

struct SearchResultView: View {
    let result: TickerSearchResult
    @ObservedObject var store: DashboardStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(result.ticker)
                    .font(.system(size: 34, weight: .black, design: .rounded))
                Spacer()
                Button {
                    store.toggleWatch(result.ticker)
                } label: {
                    Label(store.isWatched(result.ticker) ? "已关注" : "关注", systemImage: store.isWatched(result.ticker) ? "star.fill" : "star")
                }
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 300), spacing: 14)], spacing: 14) {
                ForEach(result.appearances) { token in
                    TokenCard(token: token, isWatched: store.isWatched(token.ticker)) {
                        store.toggleWatch(token.ticker)
                    } open: {
                        store.selectedTicker = token
                    }
                }
            }
        }
    }
}

struct TokenCard: View {
    let token: TokenItem
    let isWatched: Bool
    let toggleWatch: () -> Void
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(token.ticker)
                                .font(.system(size: 28, weight: .black, design: .rounded))
                            ToneBadge(text: token.currentStage ?? token.stage ?? "观察", tone: token.tone)
                        }
                        Text(token.sectionLabel ?? token.primaryOpportunityLane ?? token.opportunityStructure ?? "公开信号")
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(action: toggleWatch) {
                        Image(systemName: isWatched ? "star.fill" : "star")
                    }
                    .buttonStyle(.borderless)
                }

                Text(token.reasonText)
                    .lineLimit(3)
                    .font(.callout)
                    .foregroundStyle(.secondary)

                MetricRow(token: token)

                if let signal = token.entryWindowSignal ?? token.earlyEntrySignal {
                    SignalScoreBar(signal: signal)
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard(radius: 20)
        }
        .buttonStyle(.plain)
    }
}

struct TokenDetailView: View {
    let token: TokenItem
    @ObservedObject var store: DashboardStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            AppBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(token.ticker)
                                .font(.system(size: 46, weight: .black, design: .rounded))
                            HStack {
                                ToneBadge(text: token.currentStage ?? token.stage ?? "观察", tone: token.tone)
                                ToneBadge(text: token.opportunityStructure ?? "结构未明", tone: .warm)
                                ToneBadge(text: token.direction ?? "中性", tone: .good)
                            }
                        }
                        Spacer()
                        Button {
                            store.toggleWatch(token.ticker)
                        } label: {
                            Label(store.isWatched(token.ticker) ? "已关注" : "关注", systemImage: store.isWatched(token.ticker) ? "star.fill" : "star")
                        }
                        Button("关闭") { dismiss() }
                    }
                    .padding(18)
                    .glassCard(radius: 24)

                    Text(token.reasonText)
                        .font(.title3)
                        .foregroundStyle(.secondary)
                        .padding(18)
                        .glassCard(radius: 20)

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        DetailMetric(title: "标记价格", value: token.priceText)
                        DetailMetric(title: "24h 涨跌", value: token.percentText(token.market?.priceChangePercent ?? token.price24h))
                        DetailMetric(title: "资金费率", value: token.fundingText)
                        DetailMetric(title: "热度分", value: "\(token.heatScore ?? 0)")
                        DetailMetric(title: "OI 1h", value: token.percentText(token.oiValue(.h1)))
                        DetailMetric(title: "OI 6h", value: token.percentText(token.oiValue(.h6)))
                    }

                    GateList(gates: token.strategyLayer?.gates ?? token.gates ?? [])
                    SignalDetail(title: "入场窗口信号", signal: token.entryWindowSignal)
                    SignalDetail(title: "早发现信号", signal: token.earlyEntrySignal)
                    EvidenceBlock(title: token.oiSignal?.label ?? "OI 信号", reason: token.oiSignal?.reason, evidence: token.oiSignal?.evidence)
                    EvidenceBlock(title: token.volumeSignal?.label ?? "量能信号", reason: token.volumeSignal?.reason, evidence: token.volumeSignal?.evidence)
                    EvidenceBlock(title: token.fundingSignal?.label ?? "费率信号", reason: token.fundingSignal?.reason, evidence: token.fundingSignal?.evidence)
                }
                .padding(24)
            }
        }
    }
}

struct CalendarSummary: View {
    let calendar: TradingCalendar

    var body: some View {
        VStack(alignment: .trailing, spacing: 8) {
            Text("\(calendar.leverage ?? 10)x AI 纸面日历")
                .font(.caption.weight(.heavy))
                .foregroundStyle(.secondary)
            Text(calendar.returnText)
                .font(.system(size: 34, weight: .black, design: .rounded))
                .foregroundStyle((calendar.totalReturnPct ?? 0) >= 0 ? .green : .red)
            Text("\(calendar.totalDays ?? 0) 天 · \(calendar.totalTrades ?? 0) 笔")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .glassCard(radius: 20)
    }
}

struct TickerTape: View {
    var body: some View {
        HStack(spacing: 8) {
            ForEach(["OI BUILD", "FUNDING", "DEX REPEAT", "VOLUME", "SIGNAL"], id: \.self) { text in
                Text(text)
                    .font(.caption.bold())
                    .foregroundStyle(.cyan)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.white.opacity(0.55), in: Capsule())
            }
        }
    }
}

struct StatusChip: View {
    let title: String
    let value: String

    var body: some View {
        HStack {
            Text(title)
                .font(.callout.weight(.bold))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.headline)
        }
        .padding(14)
        .glassCard(radius: 18)
    }
}

struct OverviewCard: View {
    let title: String
    let value: Int
    let note: String
    let tone: Tone
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(.callout.weight(.heavy))
                    .foregroundStyle(.secondary)
                Text("\(value)")
                    .font(.system(size: 34, weight: .black, design: .rounded))
                    .foregroundStyle(tone.color)
                Text(note)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .glassCard(radius: 20)
        }
        .buttonStyle(.plain)
    }
}

struct SectionHeader: View {
    let title: String
    let subtitle: String
    let count: Int

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.title2.bold())
                Text(subtitle)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text("\(count)")
                .font(.title.bold())
                .foregroundStyle(.cyan)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.white.opacity(0.55), in: RoundedRectangle(cornerRadius: 14))
        }
    }
}

struct MetricRow: View {
    let token: TokenItem

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 8) {
            MiniMetric(title: "价格", value: token.priceText)
            MiniMetric(title: "24h", value: token.percentText(token.market?.priceChangePercent ?? token.price24h))
            MiniMetric(title: "OI6h", value: token.percentText(token.oiValue(.h6)))
        }
    }
}

struct MiniMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption2.weight(.bold)).foregroundStyle(.secondary)
            Text(value).font(.callout.bold()).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(9)
        .background(.white.opacity(0.48), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct MetricTile: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).foregroundStyle(.secondary)
            Text(value).font(.title.bold())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white.opacity(0.48), in: RoundedRectangle(cornerRadius: 14))
    }
}

struct DetailMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.heavy))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.bold())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glassCard(radius: 18)
    }
}

struct ToneBadge: View {
    let text: String
    let tone: Tone

    var body: some View {
        Text(text)
            .font(.caption.weight(.heavy))
            .foregroundStyle(tone.color)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(tone.color.opacity(0.12), in: Capsule())
    }
}

struct SignalScoreBar: View {
    let signal: EntrySignal

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(signal.summary ?? "综合信号")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer()
                Text("\(signal.score ?? 0)")
                    .font(.headline.bold())
                    .foregroundStyle(.cyan)
            }
            ProgressView(value: Double(signal.score ?? 0), total: 100)
                .tint(.cyan)
        }
    }
}

struct SignalDetail: View {
    let title: String
    let signal: EntrySignal?

    var body: some View {
        if let signal {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(title).font(.headline)
                    Spacer()
                    ToneBadge(text: "\(signal.score ?? 0) / 100", tone: .good)
                }
                Text(signal.summary ?? "无摘要")
                    .foregroundStyle(.secondary)
                if let breakdown = signal.scoreBreakdown {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 120))], spacing: 8) {
                        ForEach(breakdown.sorted(by: { $0.key < $1.key }), id: \.key) { _, score in
                            MiniMetric(title: score.label ?? "score", value: "\(score.score ?? 0)/\(score.max ?? 0)")
                        }
                    }
                }
                if let rules = signal.ruleCodes, !rules.isEmpty {
                    Text(rules.joined(separator: " · "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
            .glassCard(radius: 18)
        }
    }
}

struct GateList: View {
    let gates: [Gate]

    var body: some View {
        if !gates.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("交易层闸门").font(.headline)
                ForEach(gates) { gate in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: gate.pass == true ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                            .foregroundStyle(gate.pass == true ? .green : .orange)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(gate.label ?? gate.id ?? "Gate")
                                .font(.callout.bold())
                            Text(gate.reason ?? gate.message ?? "")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding(16)
            .glassCard(radius: 18)
        }
    }
}

struct EvidenceBlock: View {
    let title: String
    let reason: String?
    let evidence: [String]?

    var body: some View {
        if reason != nil || !(evidence ?? []).isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text(title).font(.headline)
                if let reason {
                    Text(reason)
                        .foregroundStyle(.secondary)
                }
                ForEach(evidence ?? [], id: \.self) { item in
                    Label(item, systemImage: "checkmark.seal")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
            .glassCard(radius: 18)
        }
    }
}

struct FeatureStatsGrid: View {
    let stats: [FeatureStat]

    var body: some View {
        if !stats.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("共同特征").font(.headline)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 10)], spacing: 10) {
                    ForEach(stats) { stat in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(stat.label ?? "特征").font(.headline)
                            Text("\(stat.count ?? 0) 个样本 · 30%命中 \(stat.hit30Rate ?? "--")")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(stat.summary ?? "")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(12)
                        .background(.white.opacity(0.45), in: RoundedRectangle(cornerRadius: 14))
                    }
                }
            }
        }
    }
}

struct ComboGrid: View {
    let combos: [FeatureCombo]

    var body: some View {
        if !combos.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("多维交叉").font(.headline)
                ForEach(combos.prefix(5)) { combo in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(combo.label ?? combo.key ?? "组合").font(.callout.bold())
                        Text("\(combo.count ?? 0) 个样本 · 涨超30% \(combo.hit30Rate ?? "--") · 平均最高 \(combo.averageText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text((combo.sampleTickers ?? []).joined(separator: " · "))
                            .font(.caption)
                            .foregroundStyle(.cyan)
                    }
                    .padding(12)
                    .background(.white.opacity(0.45), in: RoundedRectangle(cornerRadius: 14))
                }
            }
        }
    }
}

struct WatchTickerCard: View {
    let ticker: String
    let search: () -> Void
    let remove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(ticker).font(.title.bold())
                Spacer()
                Button(action: remove) { Image(systemName: "star.fill") }
                    .buttonStyle(.borderless)
            }
            Text("当前公开摘要里没有它的完整卡片，可直接搜索历史轨迹。")
                .foregroundStyle(.secondary)
            Button("搜索 \(ticker)", action: search)
        }
        .padding(18)
        .glassCard(radius: 20)
    }
}

struct EmptyState: View {
    var text = "当前没有可显示的数据。"

    var body: some View {
        Text(text)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, minHeight: 88)
            .background(.white.opacity(0.38), in: RoundedRectangle(cornerRadius: 18))
    }
}

struct AppBackground: View {
    var body: some View {
        LinearGradient(colors: [
            Color(red: 0.90, green: 0.98, blue: 1.00),
            Color(red: 0.66, green: 0.88, blue: 1.00),
            Color(red: 0.82, green: 0.96, blue: 1.00)
        ], startPoint: .topLeading, endPoint: .bottomTrailing)
        .ignoresSafeArea()
    }
}

extension View {
    func glassCard(radius: CGFloat) -> some View {
        self
            .background(.white.opacity(0.56), in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(.white.opacity(0.72), lineWidth: 1)
            )
            .shadow(color: .cyan.opacity(0.16), radius: 24, x: 0, y: 14)
    }
}

enum DashboardSection: String, CaseIterable, Identifiable {
    case overview
    case review
    case entry
    case early
    case opportunities
    case signals
    case radar
    case breakout
    case risk
    case watchlist
    case search
    case skills
    case mirror
    case files

    var id: String { rawValue }

    static let primary: [DashboardSection] = [.overview, .review, .entry, .early, .opportunities, .signals, .radar, .breakout, .risk]

    var title: String {
        switch self {
        case .overview: "总览"
        case .review: "AI复盘"
        case .entry: "入场窗口"
        case .early: "早发现雷达"
        case .opportunities: "确认/回踩候选"
        case .signals: "信号轨迹"
        case .radar: "机会雷达"
        case .breakout: "启动复盘"
        case .risk: "风险区"
        case .watchlist: "我的关注"
        case .search: "币种搜索"
        case .skills: "悟空技能"
        case .mirror: "图片同步"
        case .files: "文件同步"
        }
    }

    var icon: String {
        switch self {
        case .overview: "gauge.with.dots.needle.bottom.50percent"
        case .review: "sparkles"
        case .entry: "scope"
        case .early: "radar"
        case .opportunities: "flag.checkered"
        case .signals: "waveform.path.ecg"
        case .radar: "dot.radiowaves.left.and.right"
        case .breakout: "chart.line.uptrend.xyaxis"
        case .risk: "exclamationmark.shield"
        case .watchlist: "star"
        case .search: "magnifyingglass"
        case .skills: "wand.and.stars"
        case .mirror: "photo.on.rectangle.angled"
        case .files: "folder.badge.gearshape"
        }
    }
}

enum RadarTab: String, CaseIterable, Identifiable {
    case oi
    case repeatPool
    case accumulation
    case market
    case futures

    var id: String { rawValue }
    var title: String {
        switch self {
        case .oi: "OI异动"
        case .repeatPool: "多次出现"
        case .accumulation: "蓄势池"
        case .market: "市场确认"
        case .futures: "合约异动"
        }
    }
}

enum Tone {
    case good
    case warm
    case hot
    case muted

    var color: Color {
        switch self {
        case .good: .green
        case .warm: .orange
        case .hot: .red
        case .muted: .secondary
        }
    }
}

struct WukongAPI {
    let baseURL = URL(string: "https://michill.ai")!
    private let snapshotPaths = [
        "/Users/wangbo/.hermes/wukong_telegram/wukong_latest_snapshot.json",
        "/Users/wangbo/Documents/New project/悟空app/wukong_latest_snapshot.json"
    ]
    private let pwaURLPaths = [
        "/Users/wangbo/.hermes/wukong_pwa/wukong_pwa_url.txt",
        "/Users/wangbo/Documents/New project/悟空app/wukong_pwa_url.txt"
    ]
    private let screenMirrorPaths = [
        "/Users/wangbo/.hermes/wukong_telegram/wukong_screen_mirror.json",
        "/Users/wangbo/Documents/New project/悟空app/wukong_screen_mirror.json"
    ]
    private let fileSyncPaths = [
        "/Users/wangbo/.hermes/wukong_telegram/wukong_file_sync.json",
        "/Users/wangbo/.hermes/wukong_pwa/wukong_file_sync.json",
        "/Users/wangbo/Documents/New project/悟空app/wukong_file_sync.json"
    ]
    let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let plain = ISO8601DateFormatter()
            plain.formatOptions = [.withInternetDateTime]
            if let date = fractional.date(from: value) ?? plain.date(from: value) {
                return date
            }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid ISO8601 date: \(value)")
        }
        return decoder
    }()

    func fetchDashboard() async throws -> PublicDashboard {
        try await get("/api/summary/public-dashboard")
    }

    func fetchReport() async throws -> PublicReportEnvelope {
        try await get("/api/agent-team/public-report")
    }

    func fetchCalendar() async throws -> TradingCalendar {
        try await get("/api/ai-trading-calendar")
    }

    func searchTicker(_ ticker: String) async throws -> TickerSearchResult {
        try await get("/api/summary/ticker/\(ticker)")
    }

    func loadLocalSnapshot() -> WukongSnapshot? {
        for path in snapshotPaths {
            let url = URL(fileURLWithPath: path)
            guard let data = try? Data(contentsOf: url) else { continue }
            if let snapshot = try? decoder.decode(WukongSnapshot.self, from: data) {
                return snapshot
            }
        }
        return nil
    }

    func loadBridgeStatus(snapshot: WukongSnapshot? = nil) -> WukongBridgeStatus {
        let snapshot = snapshot ?? loadLocalSnapshot()
        let pwaURL = readFirstLine(paths: pwaURLPaths)
        let snapshotInstallURL = snapshot?.installURL ?? ""
        let installURL = snapshotInstallURL.isEmpty ? pwaURL : snapshotInstallURL
        return WukongBridgeStatus(
            pwaURL: pwaURL,
            installURL: installURL,
            snapshotUpdatedAt: snapshot?.updatedAt,
            snapshotGeneratedAt: snapshot?.sourceGeneratedAt,
            snapshotSource: snapshot?.mode ?? "本地桥接"
        )
    }

    func loadScreenMirror() -> WukongScreenMirror? {
        for path in screenMirrorPaths {
            let url = URL(fileURLWithPath: path)
            guard let data = try? Data(contentsOf: url) else { continue }
            if let mirror = try? decoder.decode(WukongScreenMirror.self, from: data) {
                return mirror
            }
        }
        return nil
    }

    func loadFileSync() -> WukongFileSync? {
        for path in fileSyncPaths {
            let url = URL(fileURLWithPath: path)
            guard let data = try? Data(contentsOf: url) else { continue }
            if let sync = try? decoder.decode(WukongFileSync.self, from: data) {
                return sync
            }
        }
        return nil
    }

    private func readFirstLine(paths: [String]) -> String {
        for path in paths {
            if let value = try? String(contentsOfFile: path, encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines),
               value.hasPrefix("https://") {
                return value
            }
        }
        return ""
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let url = baseURL.appending(path: path)
        let (data, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try decoder.decode(T.self, from: data)
    }
}

struct WukongBridgeStatus {
    var pwaURL: String = ""
    var installURL: String = ""
    var snapshotUpdatedAt: Date?
    var snapshotGeneratedAt: Date?
    var snapshotSource: String = "等待快照"

    var snapshotText: String {
        guard let snapshotUpdatedAt else { return "等待快照" }
        return DateFormatter.short.string(from: snapshotUpdatedAt)
    }

    var installText: String {
        installURL.isEmpty ? "等待链接" : "已同步"
    }

    var telegramText: String {
        snapshotUpdatedAt == nil ? "等待推送" : "推送 + 快照"
    }
}

struct WukongSnapshot: Decodable {
    let app: String?
    let mode: String?
    let updatedAt: Date?
    let sourceGeneratedAt: Date?
    let summary: String?
    let dashboard: PublicDashboard?
    let report: PublicReportEnvelope?
    let calendar: TradingCalendar?

    var installURL: String {
        for line in (summary ?? "").split(separator: "\n") {
            if line.hasPrefix("iPhone安装：") {
                return String(line).replacingOccurrences(of: "iPhone安装：", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return ""
    }
}

struct WukongScreenMirror: Decodable {
    let source: String
    let updatedAt: Date?
    let title: String
    let subtitle: String
    let description: String
    let tags: [String]
    let calendar: WukongMirrorCalendar?
    let status: [WukongMirrorItem]
    let notice: String
    let overviewCards: [WukongMirrorCard]
    let sidebar: WukongMirrorSidebar?
    let priorityRead: WukongMirrorPriority?

    var updatedText: String {
        guard let updatedAt else { return "等待同步" }
        return DateFormatter.short.string(from: updatedAt)
    }
}

struct WukongMirrorCalendar: Decodable {
    let label: String
    let returnText: String
    let detail: String
}

struct WukongMirrorItem: Decodable, Identifiable {
    var id: String { title }
    let title: String
    let value: String
}

struct WukongMirrorCard: Decodable, Identifiable {
    var id: String { title }
    let title: String
    let value: String
    let note: String
    let tone: String?
}

struct WukongMirrorSidebar: Decodable {
    let research: [String]
    let personal: [String]
    let publicSections: [WukongMirrorItem]
}

struct WukongMirrorPriority: Decodable {
    let title: String
    let count: String
    let description: String
}

struct WukongFileSync: Decodable {
    let app: String
    let generatedAt: Date?
    let root: String
    let fileCount: Int
    let totalBytes: Int
    let roles: [String: Int]
    let files: [WukongSyncedFile]

    var roleItems: [WukongFileRole] {
        roles
            .map { WukongFileRole(title: $0.key, count: $0.value) }
            .sorted { $0.title < $1.title }
    }
}

struct WukongFileRole: Identifiable {
    var id: String { title }
    let title: String
    let count: Int
}

struct WukongSyncedFile: Decodable, Identifiable {
    var id: String { path }
    let path: String
    let role: String
    let bytes: Int
    let modifiedAt: Date?
    let sha256: String
    let mime: String
    let preview: String

    var sizeText: String {
        if bytes >= 1_048_576 { return String(format: "%.1fMB", Double(bytes) / 1_048_576) }
        if bytes >= 1024 { return String(format: "%.1fKB", Double(bytes) / 1024) }
        return "\(bytes)B"
    }

    var modifiedText: String {
        guard let modifiedAt else { return "--" }
        return DateFormatter.short.string(from: modifiedAt)
    }
}

struct PublicDashboard: Decodable {
    let generatedAt: Date?
    let sources: LooseJSON?
    let counts: DashboardCounts
    let entryWindow: [TokenItem]
    let earlyEntryRadar: [TokenItem]
    let earlyRadar: [TokenItem]
    let opportunities: [TokenItem]
    let riskWinnersReview: [TokenItem]
    let repeatCandidateWatch: [TokenItem]
    let oiAnomalyWatch: [TokenItem]
    let breakoutReview: [TokenItem]
    let delistRiskWatch: [TokenItem]
    let accumulationWatch: [TokenItem]
    let risingAttention: [TokenItem]
    let marketWatch: [TokenItem]
    let futuresMovers: [TokenItem]
    let overheated: [TokenItem]
    let recentSignalChanges: [TokenItem]
    let sections: [APIDashboardSection]?

    enum CodingKeys: String, CodingKey {
        case generatedAt, sources, counts, entryWindow, earlyEntryRadar, earlyRadar, opportunities
        case riskWinnersReview, repeatCandidateWatch, oiAnomalyWatch, breakoutReview, delistRiskWatch
        case accumulationWatch, risingAttention, marketWatch, futuresMovers, overheated, recentSignalChanges, sections
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try c.decodeIfPresent(Date.self, forKey: .generatedAt)
        sources = try c.decodeIfPresent(LooseJSON.self, forKey: .sources)
        counts = try c.decodeIfPresent(DashboardCounts.self, forKey: .counts) ?? DashboardCounts()
        entryWindow = try c.decodeIfPresent([TokenItem].self, forKey: .entryWindow) ?? []
        earlyEntryRadar = try c.decodeIfPresent([TokenItem].self, forKey: .earlyEntryRadar) ?? []
        earlyRadar = try c.decodeIfPresent([TokenItem].self, forKey: .earlyRadar) ?? []
        opportunities = try c.decodeIfPresent([TokenItem].self, forKey: .opportunities) ?? []
        riskWinnersReview = try c.decodeIfPresent([TokenItem].self, forKey: .riskWinnersReview) ?? []
        repeatCandidateWatch = try c.decodeIfPresent([TokenItem].self, forKey: .repeatCandidateWatch) ?? []
        oiAnomalyWatch = try c.decodeIfPresent([TokenItem].self, forKey: .oiAnomalyWatch) ?? []
        breakoutReview = try c.decodeIfPresent([TokenItem].self, forKey: .breakoutReview) ?? []
        delistRiskWatch = try c.decodeIfPresent([TokenItem].self, forKey: .delistRiskWatch) ?? []
        accumulationWatch = try c.decodeIfPresent([TokenItem].self, forKey: .accumulationWatch) ?? []
        risingAttention = try c.decodeIfPresent([TokenItem].self, forKey: .risingAttention) ?? []
        marketWatch = try c.decodeIfPresent([TokenItem].self, forKey: .marketWatch) ?? []
        futuresMovers = try c.decodeIfPresent([TokenItem].self, forKey: .futuresMovers) ?? []
        overheated = try c.decodeIfPresent([TokenItem].self, forKey: .overheated) ?? []
        recentSignalChanges = try c.decodeIfPresent([TokenItem].self, forKey: .recentSignalChanges) ?? []
        sections = try c.decodeIfPresent([APIDashboardSection].self, forKey: .sections)
    }

    var riskCount: Int {
        delistRiskWatch.count + overheated.count
    }

    var frontPageTokens: [TokenItem] {
        uniqueTokens(entryWindow + earlyEntryRadar + opportunities)
    }

    var allTokens: [TokenItem] {
        uniqueTokens(entryWindow + earlyEntryRadar + earlyRadar + opportunities + riskWinnersReview + repeatCandidateWatch + oiAnomalyWatch + breakoutReview + delistRiskWatch + accumulationWatch + risingAttention + marketWatch + futuresMovers + overheated + recentSignalChanges)
    }

    private func uniqueTokens(_ items: [TokenItem]) -> [TokenItem] {
        var seen = Set<String>()
        return items.filter { seen.insert($0.ticker).inserted }
    }
}

struct DashboardCounts: Decodable {
    let tickers: Int
    let entryWindow: Int
    let earlyEntryRadar: Int
    let earlyRadar: Int
    let oiAnomalyWatch: Int
    let repeatCandidateWatch: Int
    let recentSignalChanges: Int
    let delistRiskBlocked: Int

    init() {
        tickers = 0
        entryWindow = 0
        earlyEntryRadar = 0
        earlyRadar = 0
        oiAnomalyWatch = 0
        repeatCandidateWatch = 0
        recentSignalChanges = 0
        delistRiskBlocked = 0
    }

    enum CodingKeys: String, CodingKey {
        case tickers, entryWindow, earlyEntryRadar, earlyRadar, oiAnomalyWatch, repeatCandidateWatch, recentSignalChanges, delistRiskBlocked
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        tickers = try c.decodeIfPresent(Int.self, forKey: .tickers) ?? 0
        entryWindow = try c.decodeIfPresent(Int.self, forKey: .entryWindow) ?? 0
        earlyEntryRadar = try c.decodeIfPresent(Int.self, forKey: .earlyEntryRadar) ?? 0
        earlyRadar = try c.decodeIfPresent(Int.self, forKey: .earlyRadar) ?? 0
        oiAnomalyWatch = try c.decodeIfPresent(Int.self, forKey: .oiAnomalyWatch) ?? 0
        repeatCandidateWatch = try c.decodeIfPresent(Int.self, forKey: .repeatCandidateWatch) ?? 0
        recentSignalChanges = try c.decodeIfPresent(Int.self, forKey: .recentSignalChanges) ?? 0
        delistRiskBlocked = try c.decodeIfPresent(Int.self, forKey: .delistRiskBlocked) ?? 0
    }
}

struct APIDashboardSection: Decodable, Identifiable {
    let key: String
    let label: String
    let count: Int
    var id: String { key }
}

struct TokenItem: Decodable, Identifiable {
    let section: String?
    let sectionLabel: String?
    let ticker: String
    let state: String?
    let currentStage: String?
    let currentStageCode: String?
    let stage: String?
    let stageCode: String?
    let opportunityStructure: String?
    let opportunityStructureCode: String?
    let direction: String?
    let primaryOpportunityLane: String?
    let primaryOpportunityScore: Double?
    let heatScore: Int?
    let mentions: Int?
    let uniqueAuthors: Int?
    let totalViews: Int?
    let why: String?
    let reason: String?
    let nextAction: String?
    let price: Double?
    let price24h: Double?
    let fundingRate: Double?
    let oi: OIWindows?
    let market: MarketData?
    let strategyLayer: StrategyLayer?
    let gates: [Gate]?
    let entryWindowSignal: EntrySignal?
    let earlyEntrySignal: EntrySignal?
    let repeatCandidateSignal: RepeatCandidateSignal?
    let oiSignal: SignalBlock?
    let volumeSignal: SignalBlock?
    let fundingSignal: SignalBlock?
    let visibilityReasons: [VisibilityReason]?

    var id: String {
        "\(section ?? sectionLabel ?? "token")-\(ticker)-\(stageCode ?? currentStageCode ?? state ?? "item")"
    }

    var tone: Tone {
        switch currentStageCode ?? stageCode ?? "" {
        case "CHASE", "PROBE", "ACCUMULATION_WATCH": return .good
        case "SETUP", "WAIT_PULLBACK": return .warm
        case "AVOID", "BLOCKED": return .hot
        default: return .muted
        }
    }

    var reasonText: String {
        nextAction ?? strategyLayer?.summary ?? reason ?? why ?? entryWindowSignal?.summary ?? earlyEntrySignal?.summary ?? "暂无摘要"
    }

    var priceText: String {
        guard let value = market?.markPrice ?? price else { return "暂无" }
        if value >= 100 { return String(format: "%.2f", value) }
        if value >= 1 { return String(format: "%.4f", value) }
        return String(format: "%.6f", value)
    }

    var fundingText: String {
        guard let value = market?.fundingRate ?? fundingRate else { return "暂无" }
        return String(format: "%.5f", value)
    }

    func oiValue(_ key: OIKey) -> Double? {
        let source = market?.oiWindows ?? oi
        switch key {
        case .m5: return source?.m5
        case .h1: return source?.h1
        case .h6: return source?.h6
        case .h24: return source?.h24
        case .d30: return source?.d30
        }
    }

    func percentText(_ value: Double?) -> String {
        guard let value else { return "暂无" }
        return String(format: "%+.1f%%", value)
    }
}

enum OIKey {
    case m5, h1, h6, h24, d30
}

struct MarketData: Decodable {
    let markPrice: Double?
    let priceChangePercent: Double?
    let priceChange6h: Double?
    let quoteVolume: Double?
    let fundingRate: Double?
    let confirmScore: Double?
    let oiWindows: OIWindows?
    let contractLaunchSignal: SignalBlock?
}

struct OIWindows: Decodable {
    let m5: Double?
    let h1: Double?
    let h6: Double?
    let h24: Double?
    let d30: Double?
}

struct StrategyLayer: Decodable {
    let label: String?
    let code: String?
    let nextAction: String?
    let summary: String?
    let gates: [Gate]?
}

struct Gate: Decodable, Identifiable {
    let id: String?
    let label: String?
    let pass: Bool?
    let statusLabel: String?
    let tone: String?
    let reason: String?
    let level: String?
    let message: String?
}

struct EntrySignal: Decodable {
    let active: Bool?
    let paperAllowed: Bool?
    let publicOnly: Bool?
    let confirmOnly: Bool?
    let stageCode: String?
    let summary: String?
    let ruleCodes: [String]?
    let score: Int?
    let scoreBreakdown: [String: ScoreBreakdown]?
    let venues: Venues?
}

struct ScoreBreakdown: Decodable {
    let label: String?
    let score: Int?
    let max: Int?
}

struct Venues: Decodable {
    let binance: Bool?
    let okx: Bool?
    let hyperliquid: Bool?
    let aster: Bool?
    let dex: Bool?
    let confirmCount: Int?
}

struct RepeatCandidateSignal: Decodable {
    let label: String?
    let seenCount: Int?
    let maxGainPct: Double?
    let lastSeenAt: Date?
    let riskNow: Bool?
    let reason: String?
    let evidence: [String]?
}

struct SignalBlock: Decodable {
    let type: String?
    let label: String?
    let score: Int?
    let reason: String?
    let evidence: [String]?
}

struct VisibilityReason: Decodable {
    let code: String?
    let label: String?
    let detail: String?
    let tone: String?
}

struct PublicReportEnvelope: Decodable {
    let generatedAt: Date?
    let reviewDate: String?
    let timezone: String?
    let counts: PublicReportCounts?
    let publicReport: PublicReport?
}

struct PublicReportCounts: Decodable {
    let appearedToday: Int?
    let trustedReturns: Int?
    let hit10: Int?
    let hit30: Int?
    let riskOrBlocked: Int?
    let rawOnly: Int?
}

struct PublicReport: Decodable {
    let headline: String?
    let analysis: String?
    let aiConclusion: String?
    let updateSchedule: String?
    let riskNote: String?
    let dataNote: String?
    let aiPublicHighlights: [String]?
    let featureStats: [FeatureStat]?
    let featureCombos: [FeatureCombo]?
}

struct FeatureStat: Decodable, Identifiable {
    let label: String?
    let count: Int?
    let hit10: Int?
    let hit30: Int?
    let hit10Rate: String?
    let hit30Rate: String?
    let avgMaxGainPct: Double?
    let avgCurrentGainPct: Double?
    let summary: String?
    var id: String { label ?? UUID().uuidString }
}

struct FeatureCombo: Decodable, Identifiable {
    let key: String?
    let label: String?
    let count: Int?
    let hit10Rate: String?
    let hit30Rate: String?
    let avgMaxGainPct: Double?
    let sampleTickers: [String]?
    let summary: String?
    var id: String { key ?? label ?? UUID().uuidString }
    var averageText: String {
        guard let avgMaxGainPct else { return "--" }
        return String(format: "%+.1f%%", avgMaxGainPct)
    }
}

struct TradingCalendar: Decodable {
    let generatedAt: Date?
    let updatedAt: Date?
    let leverage: Int?
    let totalReturnPct: Double?
    let totalPnlUsdt: Double?
    let totalDays: Int?
    let totalTrades: Int?
    let days: [TradingDay]?

    var returnText: String {
        guard let totalReturnPct else { return "--" }
        return String(format: "%+.1f%%", totalReturnPct)
    }
}

struct TradingDay: Decodable, Identifiable {
    let date: String
    let bestReturnPct: Double?
    let tradeCount: Int?
    let trades: [Trade]?
    var id: String { date }
}

struct Trade: Decodable, Identifiable {
    let id: String
    let ticker: String?
    let symbol: String?
    let side: String?
    let status: String?
    let returnPct: Double?
}

struct TickerSearchResult: Decodable {
    let generatedAt: Date?
    let ticker: String
    let found: Bool
    let appearances: [TokenItem]

    enum CodingKeys: String, CodingKey {
        case generatedAt, ticker, found, appearances
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try c.decodeIfPresent(Date.self, forKey: .generatedAt)
        ticker = try c.decodeIfPresent(String.self, forKey: .ticker) ?? ""
        found = try c.decodeIfPresent(Bool.self, forKey: .found) ?? false
        appearances = try c.decodeIfPresent([TokenItem].self, forKey: .appearances) ?? []
    }
}

enum LooseJSON: Decodable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: LooseJSON])
    case array([LooseJSON])
    case null

    init(from decoder: Decoder) throws {
        if let container = try? decoder.singleValueContainer() {
            if container.decodeNil() {
                self = .null
            } else if let value = try? container.decode(Bool.self) {
                self = .bool(value)
            } else if let value = try? container.decode(Double.self) {
                self = .number(value)
            } else if let value = try? container.decode(String.self) {
                self = .string(value)
            } else if let value = try? container.decode([LooseJSON].self) {
                self = .array(value)
            } else if let value = try? container.decode([String: LooseJSON].self) {
                self = .object(value)
            } else {
                self = .null
            }
        } else {
            self = .null
        }
    }
}

extension DateFormatter {
    static let short: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "MM-dd HH:mm"
        return formatter
    }()
}

extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
