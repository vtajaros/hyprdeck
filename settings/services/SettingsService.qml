pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string rootPath: Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprland-keybind-studio")

    property var options: []
    property var draftValues: ({})
    property var pendingResets: ({})
    property bool includeInstalled: false
    property bool overridesPresent: false
    property string overridesSha256: "absent"
    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""

    readonly property bool hasUnsavedChanges: {
        return Object.keys(draftValues).length > 0 || Object.keys(pendingResets).length > 0;
    }

    property var _pendingPreview: ({})

    function effectiveValue(opt) {
        if (!opt) return null;
        if (root.pendingResets.hasOwnProperty(opt.id)) {
            return opt.live_value;
        }
        if (root.draftValues.hasOwnProperty(opt.id)) {
            return root.draftValues[opt.id];
        }
        return opt.effective_value;
    }

    function isOptionModified(opt) {
        if (!opt) return false;
        return root.draftValues.hasOwnProperty(opt.id) || root.pendingResets.hasOwnProperty(opt.id);
    }

    function hasOverride(opt) {
        if (!opt) return false;
        return opt.override_value !== null && opt.override_value !== undefined;
    }

    function setDraft(optId, val) {
        var nextDraft = Object.assign({}, root.draftValues);
        nextDraft[optId] = val;
        var nextResets = Object.assign({}, root.pendingResets);
        delete nextResets[optId];
        root.draftValues = nextDraft;
        root.pendingResets = nextResets;
        root.error = "";
        root.statusMessage = "";
        schedulePreview();
    }

    function markReset(optId) {
        var nextDraft = Object.assign({}, root.draftValues);
        delete nextDraft[optId];
        var nextResets = Object.assign({}, root.pendingResets);
        nextResets[optId] = true;
        root.draftValues = nextDraft;
        root.pendingResets = nextResets;
        root.error = "";
        root.statusMessage = "";
    }

    function schedulePreview() {
        previewTimer.restart();
    }

    Timer {
        id: previewTimer
        interval: 150
        repeat: false
        onTriggered: {
            var keys = Object.keys(root.draftValues);
            if (keys.length === 0) return;
            var payload = JSON.stringify(root.draftValues);
            previewProc.running = false;
            previewProc.command = [
                "python3", "-m", "backend.cli", "settings", "preview",
                "--inline", payload, "--json"
            ];
            previewProc.running = true;
        }
    }

    Process {
        id: stateProc
        workingDirectory: root.rootPath
        command: ["python3", "-m", "backend.cli", "settings", "state", "--json"]
        stdout: StdioCollector { id: stateOut; waitForEnd: true }
        stderr: StdioCollector { id: stateErr; waitForEnd: true }
        onExited: (code, status) => {
            root.loading = false;
            if (code !== 0) {
                root.error = (stateErr.text || "").trim() || ("Failed to load settings state (exit " + code + ")");
                return;
            }
            try {
                var data = JSON.parse(stateOut.text || "{}");
                root.options = data.options || [];
                root.includeInstalled = !!data.include_installed;
                root.overridesPresent = !!data.overrides_present;
                root.overridesSha256 = data.overrides_sha256 || "absent";
            } catch (e) {
                root.error = "Failed to parse settings state: " + e.message;
            }
        }
    }

    Process {
        id: previewProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: prevOut; waitForEnd: true }
        stderr: StdioCollector { id: prevErr; waitForEnd: true }
        onExited: (code, status) => {
            try {
                var data = JSON.parse(prevOut.text || "{}");
                if (!data.ok) {
                    root.error = data.error || "Preview failed";
                }
            } catch (e) {
                if (code !== 0) {
                    root.error = (prevErr.text || "").trim() || ("Preview failed (exit " + code + ")");
                }
            }
        }
    }

    Process {
        id: revertProc
        workingDirectory: root.rootPath
        command: ["python3", "-m", "backend.cli", "settings", "revert-preview", "--json"]
        stdout: StdioCollector { id: revOut; waitForEnd: true }
        stderr: StdioCollector { id: revErr; waitForEnd: true }
        onExited: (code, status) => {
            root.busy = false;
            if (code !== 0) {
                root.error = (revErr.text || "").trim() || "Failed to revert preview";
                return;
            }
            root.reload();
        }
    }

    Process {
        id: commitProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: comOut; waitForEnd: true }
        stderr: StdioCollector { id: comErr; waitForEnd: true }
        onExited: (code, status) => {
            root.busy = false;
            try {
                var data = JSON.parse(comOut.text || "{}");
                if (data.errors && data.errors.length > 0) {
                    root.error = data.errors.join("; ");
                    return;
                }
                if (data.applied) {
                    root.draftValues = ({});
                    root.pendingResets = ({});
                    root.statusMessage = "Saved & reloaded.";
                    root.reload();
                } else {
                    root.error = "Changes were not applied.";
                }
            } catch (e) {
                root.error = (comErr.text || "").trim() || ("Save failed: " + e.message);
            }
        }
    }

    function reload() {
        root.error = "";
        root.loading = true;
        stateProc.running = false;
        stateProc.running = true;
    }

    function discard() {
        previewTimer.stop();
        root.draftValues = ({});
        root.pendingResets = ({});
        root.error = "";
        root.statusMessage = "";
        root.busy = true;
        revertProc.running = false;
        revertProc.running = true;
    }

    function save() {
        if (root.busy || !root.hasUnsavedChanges) return;
        previewTimer.stop();
        root.error = "";
        root.statusMessage = "";
        root.busy = true;
        var payload = JSON.stringify({
            changes: root.draftValues,
            resets: Object.keys(root.pendingResets)
        });
        commitProc.running = false;
        commitProc.command = [
            "python3", "-m", "backend.cli", "settings", "commit",
            "--inline", payload,
            "--apply",
            "--scan-sha256", root.overridesSha256,
            "--json"
        ];
        commitProc.running = true;
    }

    function resetSection(sectionName) {
        if (root.busy) return;
        previewTimer.stop();
        root.error = "";
        root.statusMessage = "";
        root.busy = true;
        commitProc.running = false;
        commitProc.command = [
            "python3", "-m", "backend.cli", "settings", "reset",
            "--section", sectionName,
            "--apply",
            "--scan-sha256", root.overridesSha256,
            "--json"
        ];
        commitProc.running = true;
    }
}
