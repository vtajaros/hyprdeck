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

    property var options: []
    property var devices: []
    property var deviceOverrides: ({})
    property var xkb: ({ layouts: [], variants: ({}), option_groups: [] })

    property var draftOptions: ({})
    property var draftDevices: ({})

    property bool includeInstalled: false
    property bool overridesPresent: false
    property string overridesSha256: "absent"
    property bool loading: true
    property bool busy: false
    property string error: ""
    property string warningsText: ""
    property string statusMessage: ""

    property bool countdownActive: false
    property int remainingSeconds: 0
    property real deadlineEpoch: 0

    readonly property bool hasDraftChanges: Object.keys(draftOptions).length > 0 || Object.keys(draftDevices).length > 0

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

    function findOption(optId) {
        var list = root.options || [];
        for (var i = 0; i < list.length; i++) {
            if (list[i] && list[i].id === optId) {
                return list[i];
            }
        }
        return null;
    }

    function effectiveOptionValue(optId) {
        if (root.draftOptions && root.draftOptions.hasOwnProperty(optId)) {
            return root.draftOptions[optId];
        }
        var o = findOption(optId);
        if (!o) return null;
        if (o.effective_value !== undefined) return o.effective_value;
        if (o.live_value !== undefined) return o.live_value;
        return o.value !== undefined ? o.value : null;
    }

    function setOptionDraft(optId, val) {
        var next = Object.assign({}, root.draftOptions);
        var o = findOption(optId);
        var baseVal = o ? (o.effective_value !== undefined ? o.effective_value : (o.live_value !== undefined ? o.live_value : o.value)) : undefined;
        if (o && baseVal === val) {
            delete next[optId];
        } else {
            next[optId] = val;
        }
        root.draftOptions = next;
        root.error = "";
        root.statusMessage = "";
    }

    function effectiveDeviceField(devObj, fieldName) {
        if (!devObj) return null;
        var name = devObj.name || "";
        var d = root.draftDevices[name];
        if (d && d.hasOwnProperty(fieldName)) {
            return d[fieldName];
        }
        var ov = root.deviceOverrides[name];
        if (ov && ov.hasOwnProperty(fieldName)) {
            return ov[fieldName];
        }
        return devObj[fieldName];
    }

    function setDeviceDraft(devName, fieldName, val) {
        var next = Object.assign({}, root.draftDevices);
        var entry = Object.assign({}, root.deviceOverrides[devName] || {}, next[devName] || {});
        entry[fieldName] = val;
        next[devName] = entry;
        root.draftDevices = next;
        root.error = "";
        root.statusMessage = "";
    }

    function clearDeviceDraft(devName) {
        var next = Object.assign({}, root.draftDevices);
        delete next[devName];
        root.draftDevices = next;
        root.error = "";
        root.statusMessage = "";
    }

    function discardDrafts() {
        root.draftOptions = ({});
        root.draftDevices = ({});
        root.error = "";
        root.warningsText = "";
        root.statusMessage = "";
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
                root.draftOptions = ({});
                root.draftDevices = ({});
                root.statusMessage = "Input settings reverted after timeout.";
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
                root.error = (stateErr.text || "").trim() || ("Failed to load input state (exit " + code + ")");
                return;
            }
            try {
                var data = JSON.parse(stateOut.text || "{}");
                root.options = data.options || [];
                root.devices = data.devices || [];
                root.deviceOverrides = data.device_overrides || ({});
                root.xkb = data.xkb || ({ layouts: [], variants: ({}), option_groups: [] });
                root.includeInstalled = !!data.include_installed;
                root.overridesPresent = !!data.overrides_present;
                root.overridesSha256 = data.overrides_sha256 || "absent";
                if (data.devices_error) {
                    root.error = String(data.devices_error);
                } else if (data.xkb_error) {
                    root.error = String(data.xkb_error);
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
                root.error = "Failed to parse input state: " + e.message;
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
                if (data.warnings && data.warnings.length > 0) {
                    root.warningsText = data.warnings.join("; ");
                } else {
                    root.warningsText = "";
                }
                if (data.errors && data.errors.length > 0) {
                    root.countdownActive = false;
                    countdownTimer.stop();
                    root.error = data.errors.join("; ");
                    return;
                }
                if (data.applied) {
                    if (data.requires_confirm) {
                        root.deadlineEpoch = Number(data.deadline_epoch || (Date.now() / 1000.0 + root.debugTimeoutSeconds));
                        root.remainingSeconds = Math.max(1, Math.ceil(root.deadlineEpoch - (Date.now() / 1000.0)));
                        root.countdownActive = true;
                        countdownTimer.restart();
                    } else {
                        root.draftOptions = ({});
                        root.draftDevices = ({});
                        root.statusMessage = "Input settings saved.";
                        root.reload();
                    }
                } else {
                    root.error = "Input changes were not applied.";
                }
            } catch (e) {
                root.error = (applyErr.text || "").trim() || ("Input apply failed: " + e.message);
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
                    root.draftOptions = ({});
                    root.draftDevices = ({});
                    root.statusMessage = "Input settings saved & kept.";
                    root.reload();
                } else {
                    root.error = String(data.error || "Failed to confirm input changes.");
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
                    root.draftOptions = ({});
                    root.draftDevices = ({});
                    root.statusMessage = "Input settings reverted.";
                    root.reload();
                } else {
                    root.error = String(data.error || "Failed to revert input changes.");
                }
            } catch (e) {
                root.error = (revErr.text || "").trim() || ("Revert failed: " + e.message);
            }
        }
    }

    function reload() {
        root.error = "";
        root.loading = true;
        var cmd = ["python3", "-m", "backend.cli", "settings", "input", "state", "--json"];
        _appendDebugArgs(cmd);
        stateProc.running = false;
        stateProc.command = cmd;
        stateProc.running = true;
    }

    function applyChanges(optionalInlinePayload) {
        if (root.busy || root.countdownActive) return;
        var payloadObj;
        if (optionalInlinePayload !== undefined && optionalInlinePayload !== null) {
            payloadObj = optionalInlinePayload;
        } else {
            payloadObj = {
                options: root.draftOptions,
                devices: root.draftDevices
            };
        }
        var hasOpts = payloadObj.options && Object.keys(payloadObj.options).length > 0;
        var hasDevs = payloadObj.devices && Object.keys(payloadObj.devices).length > 0;
        if (!hasOpts && !hasDevs) {
            root.error = "No pending input changes to apply.";
            return;
        }
        root.error = "";
        root.warningsText = "";
        root.statusMessage = "";
        root.busy = true;
        var cmd = [
            "python3", "-m", "backend.cli", "settings", "input", "apply",
            "--inline", JSON.stringify(payloadObj),
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
        confirmProc.command = ["python3", "-m", "backend.cli", "settings", "input", "confirm", "--json"];
        confirmProc.running = true;
    }

    function revertChanges() {
        if (root.busy) return;
        countdownTimer.stop();
        root.error = "";
        root.busy = true;
        var cmd = ["python3", "-m", "backend.cli", "settings", "input", "revert", "--json"];
        if (root.debugMode && root.debugReloadMode === "none") {
            cmd.push("--no-live");
        }
        revertProc.running = false;
        revertProc.command = cmd;
        revertProc.running = true;
    }
}
