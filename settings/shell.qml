import QtQuick
import Quickshell
import Quickshell.Io
import "services"

ShellRoot {
    id: root

    readonly property bool debugEnabled: Quickshell.env("HKS_SETTINGS_DEBUG") === "1"

    function _debugDisabledJson() {
        return JSON.stringify({ ok: false, error: "debug mode disabled" });
    }

    function _parseJsonArg(raw) {
        if (raw === undefined || raw === null) return raw;
        var s = String(raw).trim();
        if (s.length === 0) return "";
        try {
            return JSON.parse(s);
        } catch (e) {
            return String(raw);
        }
    }

    IpcHandler {
        target: AppInfo.ipcTarget

        function open() {
            winLoader.item.openWindow();
        }

        function toggle() {
            winLoader.item.toggleWindow();
        }

        function close() {
            winLoader.item.closeWindow(false);
        }

        function reload() {
            SettingsService.reload();
            DisplayService.reload();
            AudioService.reload(false);
            BluetoothService.reload(false);
            NetworkService.reload(false);
            ThemesService.reload(false);
            PowerService.reload(false);
            SystemService.reload();
            KeyboardService.reload();
        }

        function navigate(page: string) {
            winLoader.item.navigate(page);
        }

        function debugSet(id: string, jsonValue: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var val = root._parseJsonArg(jsonValue);
            SettingsService.setDraft(String(id), val);
            return JSON.stringify({ ok: true, id: String(id), value: val });
        }

        function debugSave(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            SettingsService.save();
            return JSON.stringify({ ok: true });
        }

        function debugDiscard(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            SettingsService.discard();
            return JSON.stringify({ ok: true });
        }

        function debugReset(section: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            SettingsService.resetSection(String(section));
            return JSON.stringify({ ok: true, section: String(section) });
        }

        function debugDisplayApply(jsonChanges: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var parsed = null;
            try {
                parsed = JSON.parse(String(jsonChanges));
            } catch (e) {
                return JSON.stringify({ ok: false, error: "Invalid JSON changes: " + e.message });
            }
            DisplayService.applyChanges(parsed);
            return JSON.stringify({ ok: true });
        }

        function debugDisplayKeep(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            DisplayService.keepChanges();
            return JSON.stringify({ ok: true });
        }

        function debugDisplayRevert(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            DisplayService.revertChanges();
            return JSON.stringify({ ok: true });
        }

        function debugInputApply(jsonChanges: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var parsed = null;
            try {
                parsed = JSON.parse(String(jsonChanges));
            } catch (e) {
                return JSON.stringify({ ok: false, error: "Invalid JSON changes: " + e.message });
            }
            InputService.applyChanges(parsed);
            return JSON.stringify({ ok: true });
        }

        function debugInputKeep(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            InputService.keepChanges();
            return JSON.stringify({ ok: true });
        }

        function debugInputRevert(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            InputService.revertChanges();
            return JSON.stringify({ ok: true });
        }

        function debugAudioState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: AudioService.available,
                defaultSink: AudioService.defaultSink,
                defaultSource: AudioService.defaultSource,
                outputs: AudioService.outputs,
                inputs: AudioService.inputs,
                streams: AudioService.streams,
                loading: AudioService.loading,
                busy: AudioService.busy,
                error: AudioService.error,
                statusMessage: AudioService.statusMessage
            });
        }

        function debugAudioSetVolume(kind: string, name: string, percent: int): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
            var n = String(name || "").trim();
            if (n.length === 0) {
                return JSON.stringify({ ok: false, error: "name is required" });
            }
            AudioService.setVolume(k, n, percent);
            return JSON.stringify({ ok: true, kind: k, name: n, percent: percent });
        }

        function debugAudioSetMute(kind: string, name: string, mode: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
            var n = String(name || "").trim();
            var m = String(mode || "toggle").trim();
            if (n.length === 0) {
                return JSON.stringify({ ok: false, error: "name is required" });
            }
            AudioService.setMute(k, n, m);
            return JSON.stringify({ ok: true, kind: k, name: n, mode: m });
        }

        function debugBluetoothState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: BluetoothService.available,
                noController: BluetoothService.noController,
                controller: BluetoothService.controller,
                rfkill: BluetoothService.rfkill,
                devices: BluetoothService.devices,
                safety: BluetoothService.safety,
                confirmOpen: BluetoothService.confirmOpen,
                confirmTitle: BluetoothService.confirmTitle,
                confirmMessage: BluetoothService.confirmMessage,
                loading: BluetoothService.loading,
                busy: BluetoothService.busy,
                error: BluetoothService.error,
                statusMessage: BluetoothService.statusMessage
            });
        }

        function debugBluetoothSetPairable(enabled: bool): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            BluetoothService.setPairable(!!enabled);
            return JSON.stringify({ ok: true, pairable: !!enabled });
        }

        function debugBluetoothRequestPowerOff(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            BluetoothService.requestPower(false);
            return JSON.stringify({
                ok: true,
                confirmOpen: BluetoothService.confirmOpen,
                confirmTitle: BluetoothService.confirmTitle,
                confirmMessage: BluetoothService.confirmMessage
            });
        }

        function debugBluetoothCancelConfirm(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            BluetoothService.cancelPending();
            return JSON.stringify({ ok: true, confirmOpen: BluetoothService.confirmOpen });
        }

        function debugNetworkState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: NetworkService.available,
                general: NetworkService.general,
                hasWifiDevice: NetworkService.hasWifiDevice,
                devices: NetworkService.devices,
                debugDevices: NetworkService.debugDevices,
                connections: NetworkService.connections,
                wifiNetworks: NetworkService.wifiNetworks,
                safety: NetworkService.safety,
                confirmOpen: NetworkService.confirmOpen,
                confirmTitle: NetworkService.confirmTitle,
                confirmMessage: NetworkService.confirmMessage,
                loading: NetworkService.loading,
                busy: NetworkService.busy,
                error: NetworkService.error,
                statusMessage: NetworkService.statusMessage
            });
        }

        function debugNetworkRequestDisconnect(deviceName: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var target = null;
            var devs = NetworkService.devices || [];
            for (var i = 0; i < devs.length; i++) {
                if (devs[i] && devs[i].name === String(deviceName)) {
                    target = devs[i];
                    break;
                }
            }
            if (!target) {
                return JSON.stringify({ ok: false, error: "Unknown device: " + String(deviceName) });
            }
            if (!target.would_cut_current_session) {
                return JSON.stringify({
                    ok: true,
                    confirmOpen: false,
                    wouldCutSession: false,
                    device: target.name
                });
            }
            NetworkService.requestDisconnect(target);
            return JSON.stringify({
                ok: true,
                confirmOpen: NetworkService.confirmOpen,
                confirmTitle: NetworkService.confirmTitle,
                confirmMessage: NetworkService.confirmMessage,
                wouldCutSession: true
            });
        }

        function debugNetworkCancelConfirm(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            NetworkService.cancelPending();
            return JSON.stringify({ ok: true, confirmOpen: NetworkService.confirmOpen });
        }

        function debugThemesState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: ThemesService.available,
                wallpaper: ThemesService.wallpaper,
                gtk: ThemesService.gtk,
                icons: ThemesService.icons,
                cursor: ThemesService.cursor,
                qt: ThemesService.qt,
                colorScheme: ThemesService.colorScheme,
                conflicts: ThemesService.conflicts,
                loading: ThemesService.loading,
                busy: ThemesService.busy,
                error: ThemesService.error,
                statusMessage: ThemesService.statusMessage
            });
        }

        function debugThemesSetCursor(name: string, size: int): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            ThemesService.setCursor(String(name || ""), Number(size || 24));
            return JSON.stringify({ ok: true, name: String(name || ""), size: Number(size || 24) });
        }

        function debugThemesConflicts(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({ ok: true, conflicts: ThemesService.conflicts });
        }

        function debugPowerState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: PowerService.available,
                battery: PowerService.battery,
                cpu: PowerService.cpu,
                hypridle: PowerService.hypridle,
                lidSleep: PowerService.lidSleep,
                capabilities: PowerService.capabilities,
                confirmOpen: PowerService.confirmOpen,
                loading: PowerService.loading,
                busy: PowerService.busy,
                error: PowerService.error,
                statusMessage: PowerService.statusMessage
            });
        }

        function debugPowerRequestTurboOff(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            PowerService.requestTurbo(false);
            return JSON.stringify({
                ok: true,
                confirmOpen: PowerService.confirmOpen,
                confirmTitle: PowerService.confirmTitle,
                confirmMessage: PowerService.confirmMessage
            });
        }

        function debugPowerCancelConfirm(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            PowerService.cancelPending();
            return JSON.stringify({ ok: true, confirmOpen: PowerService.confirmOpen });
        }

        function debugSystemInfo(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: SystemService.available,
                loading: SystemService.loading,
                info: SystemService.info,
                error: SystemService.error
            });
        }

        function debugKeyboardState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            return JSON.stringify({
                ok: true,
                available: KeyboardService.available,
                scriptPath: KeyboardService.scriptPath,
                hksWindowOpen: KeyboardService.hksWindowOpen,
                hksRunning: KeyboardService.hksRunning,
                loading: KeyboardService.loading,
                busy: KeyboardService.busy,
                error: KeyboardService.error,
                statusMessage: KeyboardService.statusMessage
            });
        }

        function debugSetInputView(tabName: string, xkbExpanded: bool): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var pg = winLoader.item ? winLoader.item.inputPageRef : null;
            if (!pg) return JSON.stringify({ ok: false, error: "inputPage not loaded" });
            if (tabName && String(tabName).length > 0) {
                pg.activeTab = String(tabName);
            }
            pg.xkbExpanded = !!xkbExpanded;
            return JSON.stringify({ ok: true, activeTab: pg.activeTab, xkbExpanded: pg.xkbExpanded });
        }

        function debugConfigureLayoutProbe(winW: int, winH: int, page: string, subTab: string, detailsOn: bool, expandAll: bool): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var winItem = winLoader.item;
            if (!winItem) return JSON.stringify({ ok: false, error: "window not loaded" });
            winItem.debugOverrideWidth = winW > 0 ? winW : 0;
            winItem.debugOverrideHeight = winH > 0 ? winH : 0;
            if (winW > 0) {
                winItem.implicitWidth = winW;
                winItem.width = winW;
            }
            if (winH > 0) {
                winItem.implicitHeight = winH;
                winItem.height = winH;
            }
            if (winItem.globalSearchRef) {
                winItem.globalSearchRef.text = "";
            }
            if (page && String(page).length > 0) {
                winItem.currentPage = String(page);
            }
            var inp = winItem.pageItemById("input");
            if (inp) {
                if (subTab && String(subTab).length > 0) inp.activeTab = String(subTab);
                inp.xkbExpanded = !!expandAll;
            }
            var aud = winItem.pageItemById("audio");
            if (aud) {
                if (aud.hasOwnProperty("showDetails")) aud.showDetails = !!detailsOn;
                if (aud.hasOwnProperty("showInactiveOutputs")) aud.showInactiveOutputs = !!expandAll;
                if (aud.hasOwnProperty("showInactiveInputs")) aud.showInactiveInputs = !!expandAll;
            }
            var net = winItem.pageItemById("network");
            if (net && net.hasOwnProperty("showDetails")) {
                net.showDetails = !!detailsOn;
            }
            var thm = winItem.pageItemById("themes");
            if (thm) {
                if (thm.hasOwnProperty("showAllIcons")) thm.showAllIcons = !!expandAll;
                if (thm.hasOwnProperty("showAllCursors")) thm.showAllCursors = !!expandAll;
                if (thm.hasOwnProperty("expandConflicts")) thm.expandConflicts = !!detailsOn;
            }
            return JSON.stringify({
                ok: true,
                winWidth: winItem.effectiveWinWidth,
                winHeight: winItem.effectiveWinHeight,
                currentPage: winItem.currentPage
            });
        }

        function debugGrabWindowToFile(outPath: string): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var winItem = winLoader.item;
            if (!winItem || !winItem.rootSurfaceRef) {
                return JSON.stringify({ ok: false, error: "rootSurface not loaded" });
            }
            var path = String(outPath || "").trim();
            if (path.length === 0) {
                return JSON.stringify({ ok: false, error: "outPath required" });
            }
            var targetSeq = winItem.lastGrabSeq + 1;
            winItem.lastGrabStatus = "pending:" + targetSeq;
            var started = winItem.rootSurfaceRef.grabToImage(function(res) {
                var saved = res ? res.saveToFile(path) : false;
                winItem.lastGrabSeq = targetSeq;
                winItem.lastGrabStatus = (saved ? "ok:" : "fail:") + targetSeq + ":" + path;
            });
            return JSON.stringify({ ok: !!started, seq: targetSeq, path: path });
        }

        function debugGrabStatus(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var winItem = winLoader.item;
            if (!winItem) return JSON.stringify({ ok: false, error: "window not loaded" });
            return JSON.stringify({ ok: true, seq: winItem.lastGrabSeq, status: winItem.lastGrabStatus });
        }

        function debugAuditCurrentLayout(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var winItem = winLoader.item;
            if (!winItem) return JSON.stringify({ ok: false, error: "window not loaded" });
            var pageRoot = winItem.activePageItem();
            if (!pageRoot) return JSON.stringify({ ok: false, error: "no active page" });

            var violations = [];
            var overlapLeaves = [];

            function _itemLabel(it) {
                if (!it) return "Item";
                if (it.objectName && it.objectName.length > 0) return it.objectName;
                if (_isActionBtn(it)) {
                    return "Button(\"" + String(it.text || "") + "\")";
                }
                if (it.text !== undefined && String(it.text).length > 0) {
                    var s = String(it.text).replace(/\s+/g, " ").trim();
                    if (s.length > 28) s = s.slice(0, 28) + "...";
                    return "Text(\"" + s + "\")";
                }
                if (it.placeholderText !== undefined && String(it.placeholderText).length > 0) {
                    return "TextField(\"" + String(it.placeholderText) + "\")";
                }
                return it.toString().split("(")[0];
            }

            function _isActionBtn(it) {
                return it && it.compact !== undefined && it.variant !== undefined && it.horizontalPadding !== undefined;
            }

            function _isTextItem(it) {
                return it && it.contentWidth !== undefined && it.elide !== undefined && it.wrapMode !== undefined && it.maximumLineCount !== undefined;
            }

            function _isTextInputControl(it) {
                return it && ((it.placeholderText !== undefined && it.background !== undefined) || (it.placeholder !== undefined && it.forceFocus !== undefined));
            }

            function _hasHorizontalScrollerAncestor(it) {
                var p = it ? it.parent : null;
                while (p && p !== pageRoot) {
                    if (p.objectName === "horizontalSafetyScroller" && pageRoot.width < 320) return true;
                    p = p.parent;
                }
                return false;
            }

            function _insideVerticalScrollView(it) {
                var p = it ? it.parent : null;
                while (p && p !== pageRoot) {
                    if (p.contentWidth !== undefined && p.contentHeight !== undefined && p.interactive !== undefined) return true;
                    p = p.parent;
                }
                return false;
            }

            function _isDescendant(anc, node) {
                var p = node ? node.parent : null;
                while (p) {
                    if (p === anc) return true;
                    p = p.parent;
                }
                return false;
            }

            function _walk(node, path, inOpaque) {
                if (!node || !node.visible || node.opacity <= 0.01) return;
                if (node.width <= 0 && node.height <= 0 && node !== pageRoot) return;
                var label = _itemLabel(node);
                var curPath = path ? (path + "/" + label) : label;
                var isBtn = _isActionBtn(node);
                var isIn = _isTextInputControl(node);
                var isTxt = _isTextItem(node);
                var isOpaqueControl = isBtn || isIn;

                if (isOpaqueControl || isTxt) {
                    var pt = node.mapToItem(pageRoot, 0, 0);
                    var horizOk = _hasHorizontalScrollerAncestor(node);
                    if (!horizOk && (pt.x < -2 || (pt.x + node.width) > (pageRoot.width + 2))) {
                        violations.push({
                            type: "out_of_bounds",
                            item: label,
                            path: curPath,
                            detail: "x=" + Math.round(pt.x) + ".." + Math.round(pt.x + node.width) + " vs viewport 0.." + Math.round(pageRoot.width)
                        });
                    }
                    if (!_insideVerticalScrollView(node) && (pt.y < -2 || (pt.y + node.height) > (pageRoot.height + 2))) {
                        violations.push({
                            type: "out_of_bounds",
                            item: label,
                            path: curPath,
                            detail: "y=" + Math.round(pt.y) + ".." + Math.round(pt.y + node.height) + " vs viewport 0.." + Math.round(pageRoot.height)
                        });
                    }
                    if (isOpaqueControl && (node.width < 28 || node.height < 24)) {
                        violations.push({
                            type: "control_too_small",
                            item: label,
                            path: curPath,
                            detail: Math.round(node.width) + "x" + Math.round(node.height) + " < 28x24"
                        });
                    }
                    if (isTxt && String(node.text || "").length > 0) {
                        var isNoWrap = (node.wrapMode === Text.NoWrap);
                        var isNoElide = (node.elide === Text.ElideNone);
                        var txtCw = node.contentWidth;
                        var txtW = node.width;
                        if (isNoWrap && isNoElide && txtCw > (txtW + 2)) {
                            violations.push({
                                type: "text_clipped",
                                item: label,
                                path: curPath,
                                detail: "contentWidth=" + Math.round(txtCw) + " > width=" + Math.round(txtW)
                            });
                        } else if (!isNoElide && node.truncated === true && !(node.objectName && node.objectName.indexOf("elideOk") !== -1)) {
                            violations.push({
                                type: "text_clipped",
                                item: label,
                                path: curPath,
                                detail: "elided without elideOk mark (contentWidth=" + Math.round(txtCw) + " vs width=" + Math.round(txtW) + ")"
                            });
                        }
                    }
                    if (!inOpaque && (isOpaqueControl || isTxt)) {
                        overlapLeaves.push({ node: node, label: label, path: curPath, x1: pt.x, y1: pt.y, x2: pt.x + node.width, y2: pt.y + node.height });
                    }
                }

                var childOpaque = inOpaque || isOpaqueControl;
                var kids = node.children || [];
                for (var c = 0; c < kids.length; c++) {
                    _walk(kids[c], curPath, childOpaque);
                }
            }

            _walk(pageRoot, "", false);

            for (var a = 0; a < overlapLeaves.length; a++) {
                var la = overlapLeaves[a];
                for (var b = a + 1; b < overlapLeaves.length; b++) {
                    var lb = overlapLeaves[b];
                    if (_isDescendant(la.node, lb.node) || _isDescendant(lb.node, la.node)) continue;
                    var ox = Math.min(la.x2, lb.x2) - Math.max(la.x1, lb.x1);
                    var oy = Math.min(la.y2, lb.y2) - Math.max(la.y1, lb.y1);
                    if (ox > 2 && oy > 2) {
                        violations.push({
                            type: "overlap",
                            item: la.label + " <-> " + lb.label,
                            path: la.path + " | " + lb.path,
                            detail: "overlap " + Math.round(ox) + "x" + Math.round(oy) + "px"
                        });
                    }
                }
            }

            return JSON.stringify({
                ok: true,
                page: winItem.currentPage,
                winWidth: winItem.effectiveWinWidth,
                winHeight: winItem.effectiveWinHeight,
                viewportWidth: pageRoot.width,
                viewportHeight: pageRoot.height,
                violationCount: violations.length,
                violations: violations.slice(0, 50)
            });
        }

        function debugState(): string {
            if (!root.debugEnabled) return root._debugDisabledJson();
            var optsMap = ({});
            var allOpts = SettingsService.options || [];
            for (var i = 0; i < allOpts.length; i++) {
                var o = allOpts[i];
                if (o && o.id) {
                    optsMap[o.id] = SettingsService.effectiveValue(o);
                }
            }
            var mouseOptCount = 0;
            var touchpadOptCount = 0;
            var inOpts = InputService.options || [];
            for (var k = 0; k < inOpts.length; k++) {
                var io = inOpts[k];
                if (!io || !io.capable) continue;
                if (io.group === "Mouse") mouseOptCount++;
                else if (io.group === "Touchpad") touchpadOptCount++;
            }
            var outVis = 0; var outInact = 0;
            var aOuts = AudioService.outputs || [];
            for (var ao = 0; ao < aOuts.length; ao++) {
                var od = aOuts[ao];
                if (!od.is_default && String(od.running_state || "").toUpperCase() === "SUSPENDED") outInact++;
                else outVis++;
            }
            var inVis = 0; var inInact = 0;
            var aIns = AudioService.inputs || [];
            for (var ai = 0; ai < aIns.length; ai++) {
                var idv = aIns[ai];
                if (!idv.is_default && String(idv.running_state || "").toUpperCase() === "SUSPENDED") inInact++;
                else inVis++;
            }
            var netActiveNames = ({});
            var netDevs = NetworkService.devices || [];
            for (var nd = 0; nd < netDevs.length; nd++) {
                if (netDevs[nd] && netDevs[nd].is_active && netDevs[nd].active_connection) {
                    netActiveNames[String(netDevs[nd].active_connection)] = true;
                }
            }
            var netSavedShown = 0;
            var netConns = NetworkService.connections || [];
            for (var nc = 0; nc < netConns.length; nc++) {
                if (netConns[nc] && !(netConns[nc].name && netActiveNames[String(netConns[nc].name)])) netSavedShown++;
            }
            function _chipCount(list, cur) {
                var arr = list || [];
                var c = String(cur || "");
                var seen = ({});
                var cnt = 0;
                if (c.length > 0 && arr.indexOf(c) !== -1) { seen[c] = true; cnt++; }
                var others = 0;
                for (var idx = 0; idx < arr.length && others < 8; idx++) {
                    if (!seen[arr[idx]]) { seen[arr[idx]] = true; cnt++; others++; }
                }
                return cnt;
            }
            return JSON.stringify({
                ok: true,
                currentPage: winLoader.item ? winLoader.item.currentPage : "",
                options: optsMap,
                unsaved: Object.keys(SettingsService.draftValues || ({})),
                pendingResets: Object.keys(SettingsService.pendingResets || ({})),
                hasUnsavedChanges: SettingsService.hasUnsavedChanges,
                includeInstalled: SettingsService.includeInstalled,
                overridesSha256: SettingsService.overridesSha256,
                error: SettingsService.error,
                statusMessage: SettingsService.statusMessage,
                busy: SettingsService.busy,
                loading: SettingsService.loading,
                display: {
                    outputs: DisplayService.outputs,
                    draftOutputs: DisplayService.draftOutputs,
                    brightness: DisplayService.brightness,
                    includeInstalled: DisplayService.includeInstalled,
                    overridesSha256: DisplayService.overridesSha256,
                    countdownActive: DisplayService.countdownActive,
                    remainingSeconds: DisplayService.remainingSeconds,
                    busy: DisplayService.busy,
                    loading: DisplayService.loading,
                    error: DisplayService.error,
                    statusMessage: DisplayService.statusMessage
                },
                input: {
                    options: InputService.options,
                    mouseOptionCount: mouseOptCount,
                    touchpadOptionCount: touchpadOptCount,
                    devices: InputService.devices,
                    deviceOverrides: InputService.deviceOverrides,
                    draftOptions: InputService.draftOptions,
                    draftDevices: InputService.draftDevices,
                    includeInstalled: InputService.includeInstalled,
                    overridesSha256: InputService.overridesSha256,
                    countdownActive: InputService.countdownActive,
                    remainingSeconds: InputService.remainingSeconds,
                    busy: InputService.busy,
                    loading: InputService.loading,
                    error: InputService.error,
                    warningsText: InputService.warningsText,
                    statusMessage: InputService.statusMessage
                },
                audio: {
                    available: AudioService.available,
                    defaultSink: AudioService.defaultSink,
                    defaultSource: AudioService.defaultSource,
                    outputs: AudioService.outputs,
                    inputs: AudioService.inputs,
                    streams: AudioService.streams,
                    visibleOutputCount: outVis,
                    inactiveOutputCount: outInact,
                    visibleInputCount: inVis,
                    inactiveInputCount: inInact,
                    busy: AudioService.busy,
                    loading: AudioService.loading,
                    error: AudioService.error,
                    statusMessage: AudioService.statusMessage
                },
                bluetooth: {
                    available: BluetoothService.available,
                    noController: BluetoothService.noController,
                    controller: BluetoothService.controller,
                    rfkill: BluetoothService.rfkill,
                    devices: BluetoothService.devices,
                    safety: BluetoothService.safety,
                    confirmOpen: BluetoothService.confirmOpen,
                    busy: BluetoothService.busy,
                    loading: BluetoothService.loading,
                    error: BluetoothService.error,
                    statusMessage: BluetoothService.statusMessage
                },
                network: {
                    available: NetworkService.available,
                    general: NetworkService.general,
                    hasWifiDevice: NetworkService.hasWifiDevice,
                    devices: NetworkService.devices,
                    connections: NetworkService.connections,
                    savedShownCount: netSavedShown,
                    savedDedupedCount: netConns.length - netSavedShown,
                    wifiNetworks: NetworkService.wifiNetworks,
                    warnings: NetworkService.warnings,
                    safety: NetworkService.safety,
                    confirmOpen: NetworkService.confirmOpen,
                    busy: NetworkService.busy,
                    loading: NetworkService.loading,
                    error: NetworkService.error,
                    statusMessage: NetworkService.statusMessage
                },
                themes: {
                    available: ThemesService.available,
                    wallpaper: ThemesService.wallpaper,
                    gtk: ThemesService.gtk,
                    icons: ThemesService.icons,
                    cursor: ThemesService.cursor,
                    iconChipsShown: _chipCount(ThemesService.icons ? ThemesService.icons.installed : [], ThemesService.icons ? ThemesService.icons.gsettings_theme : ""),
                    cursorChipsShown: _chipCount(ThemesService.cursor ? ThemesService.cursor.installed : [], ThemesService.cursor ? ThemesService.cursor.gsettings_theme : ""),
                    qt: ThemesService.qt,
                    colorScheme: ThemesService.colorScheme,
                    conflicts: ThemesService.conflicts,
                    busy: ThemesService.busy,
                    loading: ThemesService.loading,
                    error: ThemesService.error
                },
                power: {
                    available: PowerService.available,
                    battery: PowerService.battery,
                    cpu: PowerService.cpu,
                    hypridle: PowerService.hypridle,
                    lidSleep: PowerService.lidSleep,
                    capabilities: PowerService.capabilities,
                    confirmOpen: PowerService.confirmOpen,
                    busy: PowerService.busy,
                    loading: PowerService.loading,
                    error: PowerService.error
                },
                system: {
                    available: SystemService.available,
                    loading: SystemService.loading,
                    info: SystemService.info,
                    error: SystemService.error
                },
                keyboard: {
                    available: KeyboardService.available,
                    scriptPath: KeyboardService.scriptPath,
                    hksWindowOpen: KeyboardService.hksWindowOpen,
                    hksRunning: KeyboardService.hksRunning,
                    loading: KeyboardService.loading,
                    busy: KeyboardService.busy,
                    error: KeyboardService.error,
                    statusMessage: KeyboardService.statusMessage
                }
            });
        }
    }

    Loader {
        id: winLoader
        source: "WindowShell.qml"
    }
}
