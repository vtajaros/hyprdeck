pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

Singleton {
    id: root

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")
    readonly property bool debugMode: Deck.env("SETTINGS_DEBUG") === "1"
    readonly property string debugConfigDir: debugMode ? (Deck.env("SETTINGS_CONFIG_DIR") || "") : ""
    readonly property string debugReloadMode: debugMode ? (Deck.env("SETTINGS_RELOAD_MODE") || "") : ""
    readonly property real debugTimeoutSeconds: {
        var raw = debugMode ? (Deck.env("SETTINGS_DISPLAY_TIMEOUT") || "") : "";
        var parsed = raw ? Number(raw) : 15.0;
        return (!isNaN(parsed) && parsed > 0) ? parsed : 15.0;
    }

    property var outputs: []
    property var draftOutputs: ({})
    property var monitorOverrides: ({})
    property var brightness: ({ available: false, device: "", current: 0, max_value: 0, percent: 100, min_percent: 5 })
    property bool includeInstalled: false
    property bool overridesPresent: false
    property string overridesSha256: "absent"
    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""

    property bool countdownActive: false
    property int remainingSeconds: 0
    property real deadlineEpoch: 0

    readonly property bool hasDraftChanges: Object.keys(draftOutputs).length > 0

    function _appendDebugArgs(cmd) {
        if (root.debugMode && root.debugConfigDir.length > 0) {
            cmd.push("--config-dir", root.debugConfigDir);
        }
        return cmd;
    }

    function _appendDebugApplyArgs(cmd) {
        _appendDebugArgs(cmd);
        if (root.debugMode && root.debugReloadMode.length > 0) {
            cmd.push("--reload-mode", root.debugReloadMode);
        }
        return cmd;
    }

    function effectiveField(outputObj, fieldName) {
        if (!outputObj) return null;
        var name = outputObj.name || "";
        var d = root.draftOutputs[name];
        if (d && d.hasOwnProperty(fieldName)) {
            return d[fieldName];
        }
        return outputObj[fieldName];
    }

    function setOutputDraft(outputName, fieldName, val) {
        var next = Object.assign({}, root.draftOutputs);
        var entry = Object.assign({}, next[outputName] || {});
        entry.output = outputName;
        entry[fieldName] = val;
        next[outputName] = entry;
        root.draftOutputs = next;
        root.error = "";
        root.statusMessage = "";
    }

    function discardDrafts() {
        root.draftOutputs = ({});
        root.error = "";
        root.statusMessage = "";
    }

    function clampBrightness(pct) {
        var n = Math.round(Number(pct) || 0);
        return Math.max(5, Math.min(100, n));
    }

    function setBrightness(pct) {
        var clamped = clampBrightness(pct);
        var nextBri = Object.assign({}, root.brightness);
        nextBri.percent = clamped;
        root.brightness = nextBri;
        root.error = "";
        if (root.debugMode && root.debugReloadMode === "none") {
            root.statusMessage = "Brightness updated (debug dry-run: " + clamped + "%).";
            return;
        }
        var cmd = ["python3", "-m", "backend.cli", "settings", "display", "brightness", "--set", String(clamped)];
        if (root.brightness && root.brightness.device) {
            cmd.push("--device", String(root.brightness.device));
        }
        cmd.push("--json");
        brightnessProc.running = false;
        brightnessProc.command = cmd;
        brightnessProc.running = true;
    }

    Timer {
        id: countdownTimer
        interval: 250
        repeat: true
        onTriggered: {
            var secsLeft = Math.ceil(root.deadlineEpoch - (Date.now() / 1000.0));
            if (secsLeft <= 0) {
                countdownTimer.stop();
                root.remainingSeconds = 0;
                root.countdownActive = false;
                root.draftOutputs = ({});
                root.statusMessage = "Display settings reverted after timeout.";
                delayedReloadTimer.restart();
            } else {
                root.remainingSeconds = secsLeft;
            }
        }
    }

    Timer {
        id: delayedReloadTimer
        interval: 350
        repeat: false
        onTriggered: root.reload()
    }

    Process {
        id: stateProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: stateOut; waitForEnd: true }
        stderr: StdioCollector { id: stateErr; waitForEnd: true }
        onExited: (code, status) => {
            root.loading = false;
            if (code !== 0) {
                root.error = (stateErr.text || "").trim() || ("Failed to load display state (exit " + code + ")");
                return;
            }
            try {
                var data = JSON.parse(stateOut.text || "{}");
                root.outputs = data.outputs || [];
                root.monitorOverrides = data.monitor_overrides || ({});
                root.brightness = data.brightness || ({ available: false, device: "", percent: 100, min_percent: 5 });
                root.includeInstalled = !!data.include_installed;
                root.overridesPresent = !!data.overrides_present;
                root.overridesSha256 = data.overrides_sha256 || "absent";
                if (data.outputs_error) {
                    root.error = String(data.outputs_error);
                }
                if (data.active_guard && data.active_guard.deadline_epoch) {
                    var rem = Math.ceil(Number(data.active_guard.deadline_epoch) - (Date.now() / 1000.0));
                    if (rem > 0) {
                        root.deadlineEpoch = Number(data.active_guard.deadline_epoch);
                        root.remainingSeconds = rem;
                        root.countdownActive = true;
                        countdownTimer.restart();
                    }
                }
            } catch (e) {
                root.error = "Failed to parse display state: " + e.message;
            }
        }
    }

    Process {
        id: brightnessProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: briOut; waitForEnd: true }
        stderr: StdioCollector { id: briErr; waitForEnd: true }
        onExited: (code, status) => {
            try {
                var data = JSON.parse(briOut.text || "{}");
                if (!data.ok && data.error) {
                    root.error = String(data.error);
                }
            } catch (e) {
                if (code !== 0) {
                    root.error = (briErr.text || "").trim() || ("Brightness failed (exit " + code + ")");
                }
            }
        }
    }

    Process {
        id: applyProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: applyOut; waitForEnd: true }
        stderr: StdioCollector { id: applyErr; waitForEnd: true }
        onExited: (code, status) => {
            root.busy = false;
            try {
                var data = JSON.parse(applyOut.text || "{}");
                if (data.errors && data.errors.length > 0) {
                    root.countdownActive = false;
                    countdownTimer.stop();
                    root.error = data.errors.join("; ");
                    return;
                }
                if (data.applied) {
                    root.deadlineEpoch = Number(data.deadline_epoch || (Date.now() / 1000.0 + root.debugTimeoutSeconds));
                    root.remainingSeconds = Math.max(1, Math.ceil(root.deadlineEpoch - (Date.now() / 1000.0)));
                    root.countdownActive = true;
                    countdownTimer.restart();
                } else {
                    root.error = "Display changes were not applied.";
                }
            } catch (e) {
                root.error = (applyErr.text || "").trim() || ("Display apply failed: " + e.message);
            }
        }
    }

    Process {
        id: confirmProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: confOut; waitForEnd: true }
        stderr: StdioCollector { id: confErr; waitForEnd: true }
        onExited: (code, status) => {
            root.busy = false;
            countdownTimer.stop();
            root.countdownActive = false;
            root.remainingSeconds = 0;
            try {
                var data = JSON.parse(confOut.text || "{}");
                if (data.ok) {
                    root.draftOutputs = ({});
                    root.statusMessage = "Display settings saved & kept.";
                    root.reload();
                } else {
                    root.error = String(data.error || "Failed to confirm display changes.");
                }
            } catch (e) {
                root.error = (confErr.text || "").trim() || ("Confirm failed: " + e.message);
            }
        }
    }

    Process {
        id: revertProc
        workingDirectory: root.rootPath
        stdout: StdioCollector { id: revOut; waitForEnd: true }
        stderr: StdioCollector { id: revErr; waitForEnd: true }
        onExited: (code, status) => {
            root.busy = false;
            countdownTimer.stop();
            root.countdownActive = false;
            root.remainingSeconds = 0;
            try {
                var data = JSON.parse(revOut.text || "{}");
                if (data.ok) {
                    root.draftOutputs = ({});
                    root.statusMessage = "Display settings reverted.";
                    root.reload();
                } else {
                    root.error = String(data.error || "Failed to revert display changes.");
                }
            } catch (e) {
                root.error = (revErr.text || "").trim() || ("Revert failed: " + e.message);
            }
        }
    }

    function reload() {
        root.error = "";
        root.loading = true;
        var cmd = ["python3", "-m", "backend.cli", "settings", "display", "state", "--json"];
        _appendDebugArgs(cmd);
        stateProc.running = false;
        stateProc.command = cmd;
        stateProc.running = true;
    }

    function applyChanges(optionalInlineChanges) {
        if (root.busy || root.countdownActive) return;
        var items = [];
        if (optionalInlineChanges !== undefined && optionalInlineChanges !== null) {
            if (Array.isArray(optionalInlineChanges)) {
                items = optionalInlineChanges;
            } else if (typeof optionalInlineChanges === "object") {
                items = [optionalInlineChanges];
            }
        } else {
            var keys = Object.keys(root.draftOutputs);
            for (var i = 0; i < keys.length; i++) {
                items.push(root.draftOutputs[keys[i]]);
            }
        }
        if (items.length === 0) {
            root.error = "No pending monitor changes to apply.";
            return;
        }
        root.error = "";
        root.statusMessage = "";
        root.busy = true;
        var payload = JSON.stringify(items);
        var cmd = [
            "python3", "-m", "backend.cli", "settings", "display", "apply",
            "--inline", payload,
            "--apply",
            "--scan-sha256", root.overridesSha256,
            "--timeout", String(root.debugTimeoutSeconds),
            "--watch-pid", "ppid",
            "--json"
        ];
        _appendDebugApplyArgs(cmd);
        applyProc.running = false;
        applyProc.command = cmd;
        applyProc.running = true;
    }

    function keepChanges() {
        if (root.busy) return;
        countdownTimer.stop();
        root.error = "";
        root.busy = true;
        confirmProc.running = false;
        confirmProc.command = ["python3", "-m", "backend.cli", "settings", "display", "confirm", "--json"];
        confirmProc.running = true;
    }

    function revertChanges() {
        if (root.busy) return;
        countdownTimer.stop();
        root.error = "";
        root.busy = true;
        var cmd = ["python3", "-m", "backend.cli", "settings", "display", "revert", "--json"];
        if (root.debugMode && root.debugReloadMode === "none") {
            cmd.push("--no-live");
        }
        revertProc.running = false;
        revertProc.command = cmd;
        revertProc.running = true;
    }
}
