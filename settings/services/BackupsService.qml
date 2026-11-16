pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

QtObject {
    id: root

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")

    property var backups: []
    property bool loading: false
    property bool diffLoading: false
    property bool restoring: false
    readonly property bool busy: loading || diffLoading || restoring

    property string error: ""
    property string statusMessage: ""
    property string lastSnapshotId: ""
    property var lastWarnings: []
    property string lastNote: ""
    property bool lastRolledBack: false

    property string selectedId: ""
    property var activeDiff: null

    property var _listProc: Process {
        command: ["python3", "-m", "backend.cli", "settings", "backups", "list", "--json"]
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.loading = false;
                try {
                    var data = JSON.parse(text);
                    if (data && data.ok) {
                        root.backups = Array.isArray(data.backups) ? data.backups : [];
                    } else {
                        root.error = (data && data.error) ? String(data.error) : "Failed to load backups.";
                    }
                } catch (e) {
                    root.error = "Failed to parse backups list.";
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                if (text && text.trim().length > 0 && root.error.length === 0) {
                    root.error = text.trim();
                }
            }
        }
    }

    property var _diffProc: Process {
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.diffLoading = false;
                try {
                    var data = JSON.parse(text);
                    if (data && data.ok) {
                        root.activeDiff = data;
                    } else {
                        root.activeDiff = null;
                        root.error = (data && data.error) ? String(data.error) : "Failed to compute diff.";
                    }
                } catch (e) {
                    root.activeDiff = null;
                    root.error = "Failed to parse backup diff.";
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                if (text && text.trim().length > 0 && root.error.length === 0) {
                    root.error = text.trim();
                }
            }
        }
    }

    property var _restoreProc: Process {
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.restoring = false;
                try {
                    var data = JSON.parse(text);
                    if (data && data.ok) {
                        root.lastRolledBack = false;
                        root.lastSnapshotId = data.snapshot_id ? String(data.snapshot_id) : "";
                        root.lastWarnings = Array.isArray(data.warnings) ? data.warnings : [];
                        root.lastNote = data.note ? String(data.note) : "";
                        root.statusMessage = "Restored " + String(data.file_name || data.restored_id || "backup") +
                            (data.reload_status && data.reload_status !== "no-reload" ? (" (" + data.reload_status + ")") : "");
                        root.reload();
                        if (root.selectedId.length > 0) {
                            root.loadDiff(root.selectedId);
                        }
                    } else {
                        root.lastRolledBack = !!(data && data.rolled_back);
                        root.lastSnapshotId = (data && data.snapshot_id) ? String(data.snapshot_id) : "";
                        root.error = (data && data.error) ? String(data.error) : "Backup restore failed.";
                        root.reload();
                    }
                } catch (e) {
                    root.error = "Failed to parse restore response.";
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                if (text && text.trim().length > 0 && root.error.length === 0) {
                    root.error = text.trim();
                }
            }
        }
    }

    function reload() {
        if (root.loading) return;
        root.loading = true;
        root.error = "";
        root._listProc.running = true;
    }

    function loadDiff(backupId) {
        var bid = String(backupId || "");
        if (bid.length === 0 || root.diffLoading) return;
        root.selectedId = bid;
        root.diffLoading = true;
        root.error = "";
        root._diffProc.command = ["python3", "-m", "backend.cli", "settings", "backups", "diff", "--id", bid, "--json"];
        root._diffProc.running = true;
    }

    function restoreBackup(backupId) {
        var bid = String(backupId || "");
        if (bid.length === 0 || root.restoring) return;
        root.restoring = true;
        root.error = "";
        root.statusMessage = "";
        root.lastWarnings = [];
        root.lastNote = "";
        root.lastRolledBack = false;
        root._restoreProc.command = ["python3", "-m", "backend.cli", "settings", "backups", "restore", "--id", bid, "--apply", "--json"];
        root._restoreProc.running = true;
    }

    function undoLastRestore() {
        if (root.lastSnapshotId.length === 0 || root.restoring) return;
        root.restoreBackup(root.lastSnapshotId);
    }

    function clearFeedback() {
        root.error = "";
        root.statusMessage = "";
        root.lastSnapshotId = "";
        root.lastWarnings = [];
        root.lastNote = "";
        root.lastRolledBack = false;
    }

    Component.onCompleted: {
        root.reload();
    }
}
