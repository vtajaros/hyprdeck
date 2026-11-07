pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool busy: false
    property string error: ""
    property var activeOp: null
    property var previewData: null
    property bool dialogOpen: false

    property string toastMessage: ""
    property bool toastVisible: false
    property bool canUndo: false

    property string companionWarning: ""
    property var backups: []
    property bool loadingBackups: false

    readonly property bool dryRunOnly: (Quickshell.env("HKS_EDIT_DRYRUN_ONLY") === "1") || !!Quickshell.env("HKS_FIXTURE")
    readonly property string rootPath: Quickshell.env("HKS_ROOT") || "."

    property var _pendingCallback: null

    Process {
        id: proc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            id: outCollector
            waitForEnd: true
        }
        stderr: StdioCollector {
            id: errCollector
            waitForEnd: true
        }
        onExited: (exitCode, exitStatus) => {
            timeoutTimer.stop();
            root.busy = false;
            var cb = root._pendingCallback;
            root._pendingCallback = null;
            if (cb) {
                var outStr = outCollector.text || "";
                var errStr = errCollector.text || "";
                var parsed = null;
                try {
                    parsed = JSON.parse(outStr);
                } catch (e) {
                    parsed = null;
                }
                cb(exitCode, parsed, errStr || outStr);
            }
        }
    }

    Timer {
        id: timeoutTimer
        interval: 15000
        repeat: false
        onTriggered: {
            if (root.busy) {
                proc.running = false;
                root.busy = false;
                root.error = "Operation timed out after 15 seconds.";
                var cb = root._pendingCallback;
                root._pendingCallback = null;
                if (cb) {
                    cb(124, null, "Operation timed out.");
                }
            }
        }
    }

    Timer {
        id: toastTimer
        interval: 8000
        repeat: false
        onTriggered: {
            root.toastVisible = false;
        }
    }

    function showToast(msg, undoable) {
        root.toastMessage = msg;
        root.canUndo = !!undoable;
        root.toastVisible = true;
        toastTimer.restart();
    }

    function hideToast() {
        root.toastVisible = false;
        toastTimer.stop();
    }

    function _exec(cmd, cb) {
        if (root.busy) return;
        root.busy = true;
        root.error = "";
        root._pendingCallback = cb;
        proc.running = false;
        proc.command = cmd;
        proc.running = true;
        timeoutTimer.restart();
    }

    function _runPreview(cmd) {
        root.error = "";
        root.previewData = null;
        _exec(cmd, function(exitCode, data, raw) {
            if (data && data.errors && data.errors.length > 0 && !data.diff) {
                root.error = data.errors.join("; ");
                return;
            }
            if (!data) {
                root.error = raw || "Failed to generate preview.";
                return;
            }
            root.previewData = data;
            if (data.warnings && data.warnings.length > 0) {
                for (var i = 0; i < data.warnings.length; i++) {
                    var w = data.warnings[i];
                    if (w.indexOf("Companion file") !== -1 || w.indexOf("hyprland.conf") !== -1) {
                        root.companionWarning = w;
                    }
                }
            }
            root.dialogOpen = true;
        });
    }

    function requestCommentOut(bind) {
        if (root.busy || !bind || !bind.id) return;
        root.activeOp = {
            action: "comment-out",
            bindId: bind.id,
            label: (bind.keys_raw || bind.key || "bind"),
            parts: KeybindData.shortcutParts(bind),
            description: (bind.description_effective ? bind.description_effective.text : ""),
            isDestructive: false,
            title: "Disable Keybinding"
        };
        _runPreview(["python3", "-m", "backend.cli", "edit", "--json", "--comment-out", bind.id]);
    }

    function requestUncomment(disabledBind) {
        if (root.busy || !disabledBind || !disabledBind.id) return;
        root.activeOp = {
            action: "uncomment",
            bindId: disabledBind.id,
            label: (disabledBind.key_hint || "disabled bind"),
            parts: KeybindData.parseShortcutString(disabledBind.key_hint),
            description: (disabledBind.description_hint || disabledBind.original_text || ""),
            isDestructive: false,
            title: "Enable Keybinding"
        };
        _runPreview(["python3", "-m", "backend.cli", "edit", "--json", "--uncomment", disabledBind.id]);
    }

    function requestDelete(bind) {
        if (root.busy || !bind || !bind.id) return;
        var parts = [];
        if (bind.modifiers || bind.key) {
            parts = KeybindData.shortcutParts(bind);
        } else if (bind.key_hint) {
            parts = KeybindData.parseShortcutString(bind.key_hint);
        } else if (bind.keys_raw) {
            parts = KeybindData.parseShortcutString(bind.keys_raw);
        }
        root.activeOp = {
            action: "delete",
            bindId: bind.id,
            label: (bind.keys_raw || bind.key_hint || bind.key || "bind"),
            parts: parts,
            description: (bind.description_effective ? bind.description_effective.text : (bind.description_hint || "")),
            isDestructive: true,
            title: "Delete Keybinding"
        };
        _runPreview(["python3", "-m", "backend.cli", "edit", "--json", "--delete", bind.id]);
    }

    function requestRestore(backupId) {
        if (root.busy || !backupId) return;
        root.activeOp = {
            action: "restore",
            backupId: backupId,
            label: "backup " + backupId,
            parts: [],
            description: "Restore configuration from backup snapshot",
            isDestructive: true,
            title: "Restore Backup"
        };
        _runPreview(["python3", "-m", "backend.cli", "restore", backupId, "--dry-run", "--json"]);
    }

    function requestRestoreLatest() {
        if (root.busy) return;
        hideToast();
        root.activeOp = {
            action: "restore-latest",
            backupId: "--latest",
            label: "latest backup",
            parts: [],
            description: "Undo last change by restoring latest snapshot",
            isDestructive: true,
            title: "Undo: Restore Latest Backup"
        };
        _runPreview(["python3", "-m", "backend.cli", "restore", "--latest", "--dry-run", "--json"]);
    }

    function cancelDialog() {
        root.dialogOpen = false;
        root.previewData = null;
        root.activeOp = null;
    }

    function confirmApply() {
        if (root.busy || !root.activeOp || root.dryRunOnly) return;
        var op = root.activeOp;
        var cmd = [];
        if (op.action === "comment-out") {
            cmd = ["python3", "-m", "backend.cli", "edit", "--json", "--apply", "--reload", "--comment-out", op.bindId];
        } else if (op.action === "uncomment") {
            cmd = ["python3", "-m", "backend.cli", "edit", "--json", "--apply", "--reload", "--uncomment", op.bindId];
        } else if (op.action === "delete") {
            cmd = ["python3", "-m", "backend.cli", "edit", "--json", "--apply", "--reload", "--delete", op.bindId];
        } else if (op.action === "restore") {
            cmd = ["python3", "-m", "backend.cli", "restore", op.backupId, "--apply", "--reload", "--json"];
        } else if (op.action === "restore-latest") {
            cmd = ["python3", "-m", "backend.cli", "restore", "--latest", "--apply", "--reload", "--json"];
        }

        root.dialogOpen = false;
        _exec(cmd, function(exitCode, data, raw) {
            if (exitCode !== 0 || !data || !data.applied) {
                var errMsg = (data && data.errors && data.errors.length > 0)
                    ? data.errors.join("; ")
                    : (raw || "Failed to apply operation.");
                root.error = errMsg;
                return;
            }
            if (data.warnings && data.warnings.length > 0) {
                for (var i = 0; i < data.warnings.length; i++) {
                    var w = data.warnings[i];
                    if (w.indexOf("Companion file") !== -1 || w.indexOf("hyprland.conf") !== -1) {
                        root.companionWarning = w;
                    }
                }
            }
            if (op.action === "comment-out") {
                showToast("Disabled " + op.label + ". Undo", true);
            } else if (op.action === "uncomment") {
                showToast("Enabled " + op.label + ". Undo", true);
            } else if (op.action === "delete") {
                showToast("Deleted " + op.label + ". Undo", true);
            } else {
                showToast("Restored configuration.", false);
            }
            loadBackups();
            KeybindData.reload();
        });
    }

    function loadBackups() {
        if (root.busy) return;
        root.loadingBackups = true;
        _exec(["python3", "-m", "backend.cli", "backups", "--json"], function(exitCode, data, raw) {
            root.loadingBackups = false;
            if (data && data.backups) {
                root.backups = data.backups;
            }
        });
    }
}
