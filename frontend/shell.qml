import QtQuick
import Quickshell
import Quickshell.Io
import "theme"
import "services"
import "components/LayoutAudit.js" as LayoutAudit

ShellRoot {
    id: root

    readonly property string mode: (Deck.env("MODE") || "window").toLowerCase()
    readonly property bool debugEnabled: Deck.env("SETTINGS_DEBUG") === "1"

    IpcHandler {
        target: "hks"
        function open() {
            if (shellLoader.item && typeof shellLoader.item.openWindow === "function") {
                shellLoader.item.openWindow();
            }
        }
        function toggle() {
            if (shellLoader.item && typeof shellLoader.item.toggleWindow === "function") {
                shellLoader.item.toggleWindow();
            } else {
                Qt.quit();
            }
        }
        function close() {
            if (shellLoader.item && typeof shellLoader.item.closeWindow === "function") {
                shellLoader.item.closeWindow();
            } else {
                Qt.quit();
            }
        }
        function reload() {
            KeybindData.reload();
        }
        function openAdd() {
            if (shellLoader.item && typeof shellLoader.item.openWindow === "function") {
                shellLoader.item.openWindow();
            }
            EditService.requestAdd();
        }
        function openEditFirst() {
            if (KeybindData.binds && KeybindData.binds.length > 0) {
                EditService.requestEdit(KeybindData.binds[0]);
            }
        }
        function debugThemeState(): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            return JSON.stringify({
                ok: true,
                themeMode: Deck.themeMode,
                colorsPath: Deck.colorsPath,
                visible: shellLoader.item ? !!shellLoader.item.visible : false,
                bg: String(Deck.bg),
                surface: String(Deck.surface),
                accent: String(Deck.accent),
                fg: String(Deck.fg)
            });
        }
        function debugState(): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            return JSON.stringify({
                ok: true,
                mode: root.mode,
                loading: !!KeybindData.loading,
                bindCount: KeybindData.binds ? KeybindData.binds.length : 0,
                conflictCount: KeybindData.conflicts ? KeybindData.conflicts.length : 0
            });
        }
        function debugConfigureLayoutProbe(winW: int, winH: int, viewName: string, searchQuery: string, categoryFilter: string): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            var item = shellLoader.item;
            if (!item) {
                return JSON.stringify({ ok: false, error: "shell not loaded" });
            }
            if (item.debugOverrideWidth !== undefined) item.debugOverrideWidth = winW > 0 ? winW : 0;
            if (item.debugOverrideHeight !== undefined) item.debugOverrideHeight = winH > 0 ? winH : 0;
            if (root.mode === "window") {
                if (winW > 0) item.implicitWidth = winW;
                if (winH > 0) item.implicitHeight = winH;
                // Reset any open dialogs cleanly
                if (item.editDialogRef && item.editDialogRef.recorderRef && item.editDialogRef.recorderRef.opened) {
                    item.editDialogRef.recorderRef.close();
                }
                if (EditService.dialogOpen) {
                    EditService.cancelDialog();
                }
                if (EditService.editDialogOpen) {
                    EditService.closeEditDialog();
                }
                var v = String(viewName || "all");
                if (v === "all" || v === "filters") {
                    item.currentPage = "all";
                    var pAll = item.activePageItem();
                    if (pAll && typeof pAll.showSearch === "function") {
                        pAll.showSearch(searchQuery || "");
                    }
                    if (pAll && pAll.hasOwnProperty("selectedCategory")) {
                        pAll.selectedCategory = categoryFilter || "All";
                    }
                } else if (v === "conflicts" || v === "disabled" || v === "backups" || v === "settings") {
                    item.currentPage = v;
                } else if (v === "add") {
                    item.currentPage = "all";
                    EditService.requestAdd();
                } else if (v === "edit" || v === "sidecar") {
                    item.currentPage = "all";
                    if (KeybindData.binds && KeybindData.binds.length > 0) {
                        EditService.requestEdit(KeybindData.binds[0]);
                    }
                } else if (v === "recorder") {
                    item.currentPage = "all";
                    EditService.requestAdd();
                    if (item.editDialogRef && item.editDialogRef.recorderRef) {
                        var rec = item.editDialogRef.recorderRef;
                        rec.recorderState = "captured";
                        rec.capturedModmask = 69;
                        rec.capturedKey = "XF86AudioRaiseVolume";
                        rec.capturedDisplay = "SUPER + SHIFT + XF86AudioRaiseVolume";
                        rec.open();
                    }
                } else if (v === "confirm") {
                    item.currentPage = "all";
                    if (KeybindData.binds && KeybindData.binds.length > 0) {
                        EditService.requestDelete(KeybindData.binds[0]);
                    }
                }
            } else if (root.mode === "card") {
                var cardAll = item.cardAllRef;
                if (cardAll && typeof cardAll.showSearch === "function") {
                    cardAll.showSearch(searchQuery || "");
                }
            } else if (root.mode === "popup") {
                var popList = item.popupListRef;
                if (popList && typeof popList.showSearch === "function") {
                    popList.showSearch(searchQuery || "");
                }
            }
            return JSON.stringify({ ok: true, mode: root.mode, view: String(viewName || "") });
        }
        function debugAuditCurrentLayout(): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            var item = shellLoader.item;
            if (!item || typeof item.activeAuditTarget !== "function") {
                return JSON.stringify({ ok: false, error: "no active audit target" });
            }
            return JSON.stringify(LayoutAudit.auditItem(item.activeAuditTarget(), { noWrap: Text.NoWrap, elideNone: Text.ElideNone }));
        }
        function debugGrabWindowToFile(outPath: string): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            var item = shellLoader.item;
            if (!item || !item.rootSurfaceRef) {
                return JSON.stringify({ ok: false, error: "rootSurface not loaded" });
            }
            var path = String(outPath || "").trim();
            if (path.length === 0) {
                return JSON.stringify({ ok: false, error: "outPath required" });
            }
            var targetSeq = item.lastGrabSeq + 1;
            item.lastGrabStatus = "pending:" + targetSeq;
            var started = item.rootSurfaceRef.grabToImage(function(res) {
                var saved = res ? res.saveToFile(path) : false;
                item.lastGrabSeq = targetSeq;
                item.lastGrabStatus = (saved ? "ok:" : "fail:") + targetSeq + ":" + path;
            });
            return JSON.stringify({ ok: !!started, seq: targetSeq, path: path });
        }
        function debugGrabStatus(): string {
            if (!root.debugEnabled) {
                return JSON.stringify({ ok: false, error: "debug mode disabled" });
            }
            var item = shellLoader.item;
            if (!item) return JSON.stringify({ ok: false, error: "shell not loaded" });
            return JSON.stringify({ ok: true, seq: item.lastGrabSeq, status: item.lastGrabStatus });
        }
    }

    Loader {
        id: shellLoader
        source: root.mode === "popup" ? "PopupShell.qml" : (root.mode === "card" ? "dev/CardHarness.qml" : (root.mode === "recorder-test" ? "dev/RecorderHarness.qml" : "WindowShell.qml"))
    }
}
