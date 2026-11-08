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

    property var targetEditBind: null
    property bool editDialogOpen: false
    property string dialogMode: "edit"
    property string lastEditedBindId: ""
    property string lastAddedShortcut: ""
    signal bindAdded(string shortcut, string key, var mods, string submap)

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

    function requestAdd() {
        if (root.busy) return;
        root.dialogMode = "add";
        root.targetEditBind = null;
        root.editDialogOpen = true;
    }

    function requestEdit(bind) {
        if (!bind || !bind.id) return;
        root.dialogMode = "edit";
        root.targetEditBind = bind;
        root.editDialogOpen = true;
    }

    function closeEditDialog() {
        root.editDialogOpen = false;
        root.targetEditBind = null;
        ConflictCheckService.reset();
        if (RecorderService.active) {
            RecorderService.leave();
        }
    }

    function previewAdd(mods, key, dispatcher, args, flags, submap, conflicts, description, category) {
        if (root.busy || !key) return;

        var cmd = [
            "python3", "-m", "backend.cli", "edit", "add",
            "--mods", mods || "",
            "--key", key,
            "--dry-run",
            "--json"
        ];
        if (dispatcher) {
            cmd.push("--dispatcher", dispatcher);
        }
        if (args) {
            cmd.push("--args", args);
        }
        if (flags) {
            cmd.push("--flags", flags);
        }
        if (submap) {
            cmd.push("--submap", submap);
        }
        if (description) {
            cmd.push("--desc", description);
        }
        if (category) {
            cmd.push("--cat", category);
        }

        var applyCmd = [
            "python3", "-m", "backend.cli", "edit", "add",
            "--mods", mods || "",
            "--key", key,
            "--apply",
            "--reload",
            "--json"
        ];
        if (dispatcher) {
            applyCmd.push("--dispatcher", dispatcher);
        }
        if (args) {
            applyCmd.push("--args", args);
        }
        if (flags) {
            applyCmd.push("--flags", flags);
        }
        if (submap) {
            applyCmd.push("--submap", submap);
        }
        if (description) {
            applyCmd.push("--desc", description);
        }
        if (category) {
            applyCmd.push("--cat", category);
        }

        var newLabel = (mods ? (mods + " + ") : "") + key;
        var parts = [];
        if (mods) {
            var mparts = mods.split("+");
            for (var i = 0; i < mparts.length; i++) {
                var mp = mparts[i].trim();
                if (mp) parts.push(mp);
            }
        }
        if (key) parts.push(key);

        root.activeOp = {
            action: "add",
            bindId: "",
            label: newLabel,
            newLabel: newLabel,
            parts: parts,
            description: (args ? (dispatcher + " " + args) : dispatcher),
            isDestructive: false,
            title: "Add Keybinding",
            conflicts: conflicts || [],
            applyCmd: applyCmd,
            addedShortcut: newLabel,
            addedKey: key,
            addedMods: mods,
            addedSubmap: submap || ""
        };

        _runPreview(cmd);
    }

    function previewReplace(bind, newMods, newKey, newDispatcher, newArgs, preserveDispatcher, conflicts, description, category) {
        if (root.busy || !bind || !bind.id) return;

        var cmd = [
            "python3", "-m", "backend.cli", "edit", "replace",
            "--id", bind.id,
            "--mods", newMods || "",
            "--key", newKey,
            "--dry-run",
            "--json"
        ];
        if (preserveDispatcher) {
            cmd.push("--preserve-dispatcher");
        } else {
            if (newDispatcher) {
                cmd.push("--dispatcher", newDispatcher);
            }
            if (newArgs) {
                cmd.push("--args", newArgs);
            }
        }
        if (description) {
            cmd.push("--desc", description);
        }
        if (category) {
            cmd.push("--cat", category);
        }

        var applyCmd = [
            "python3", "-m", "backend.cli", "edit", "replace",
            "--id", bind.id,
            "--mods", newMods || "",
            "--key", newKey,
            "--apply",
            "--reload",
            "--json"
        ];
        if (preserveDispatcher) {
            applyCmd.push("--preserve-dispatcher");
        } else {
            if (newDispatcher) {
                applyCmd.push("--dispatcher", newDispatcher);
            }
            if (newArgs) {
                applyCmd.push("--args", newArgs);
            }
        }
        if (description) {
            applyCmd.push("--desc", description);
        }
        if (category) {
            applyCmd.push("--cat", category);
        }

        var oldLabel = bind.keys_raw || bind.key || "bind";
        var newLabel = (newMods ? (newMods + " + ") : "") + newKey;

        root.activeOp = {
            action: "replace",
            bindId: bind.id,
            label: oldLabel,
            newLabel: newLabel,
            parts: KeybindData.shortcutParts(bind),
            description: (bind.description_effective ? bind.description_effective.text : ""),
            isDestructive: false,
            title: "Replace Keybinding",
            conflicts: conflicts || [],
            applyCmd: applyCmd
        };

        _runPreview(cmd);
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
        if (op.action === "replace" || op.action === "add") {
            cmd = op.applyCmd;
        } else if (op.action === "comment-out") {
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
            if (data.sidecar_warning && data.sidecar_warning.message) {
                root.showToast(data.sidecar_warning.message, false);
            } else if (op.action === "add") {
                root.lastAddedShortcut = op.newLabel || op.label;
                root.lastEditedBindId = (data && data.expected_new_bind && data.expected_new_bind.id) ? data.expected_new_bind.id : "";
                root.closeEditDialog();
                root.bindAdded(op.newLabel || op.label, op.addedKey, op.addedMods, op.addedSubmap);
                showToast("Added " + (op.newLabel || op.label) + ". Undo", true);
            } else if (op.action === "replace") {
                root.lastEditedBindId = op.bindId;
                showToast("Updated " + (op.newLabel || op.label) + ". Undo", true);
                root.closeEditDialog();
            } else if (op.action === "comment-out") {
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
            SidecarService.loadAllOverrides();
            SidecarService.loadOrphans();
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
