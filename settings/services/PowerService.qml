pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string rootPath: Quickshell.env("HYPRDECK_ROOT") || Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")
    readonly property bool debugMode: Quickshell.env("HKS_SETTINGS_DEBUG") === "1"

    property bool available: false
    property var battery: ({ available: false })
    property var cpu: ({ available: false, epp_available: [] })
    property var hypridle: ({ available: false, running: false, listeners: [] })
    property var lidSleep: ({ available: false })
    property var capabilities: ({ has_battery: false, can_write_epp: false, can_write_turbo: false, hypridle_present: false })

    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""
    property bool pollingEnabled: false

    // Confirm modal state (only for turning Turbo Boost OFF)
    property bool confirmOpen: false
    property string confirmTitle: ""
    property string confirmMessage: ""

    Timer {
        id: pollTimer
        interval: 15000
        repeat: true
        running: root.pollingEnabled && !root.busy && !stateProc.running
        onTriggered: root.reload(true)
    }

    function _applyState(data) {
        root.available = !!data.available;
        root.battery = data.battery || ({ available: false });
        root.cpu = data.cpu || ({ available: false, epp_available: [] });
        root.hypridle = data.hypridle || ({ available: false, running: false, listeners: [] });
        root.lidSleep = data.lid_sleep || ({ available: false });
        root.capabilities = data.capabilities || ({ has_battery: false, can_write_epp: false, can_write_turbo: false, hypridle_present: false });
        root.error = data.error ? String(data.error) : "";
    }

    function reload(silent) {
        if (stateProc.running) return;
        if (!silent) {
            root.loading = true;
            root.error = "";
        }
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "power", "state", "--json"];
        stateProc.running = true;
    }

    function setEpp(value) {
        _runOp(["python3", "-m", "backend.cli", "settings", "power", "epp", String(value), "--json"]);
    }

    function requestTurbo(enabled) {
        if (!enabled) {
            root.confirmTitle = "Disable CPU Turbo Boost?";
            root.confirmMessage = "Disabling Turbo Boost lowers peak CPU performance for this session (resets on reboot).";
            root.confirmOpen = true;
            return;
        }
        _runOp(["python3", "-m", "backend.cli", "settings", "power", "turbo", "on", "--json"]);
    }

    function confirmPending() {
        root.confirmOpen = false;
        root.confirmTitle = "";
        root.confirmMessage = "";
        _runOp(["python3", "-m", "backend.cli", "settings", "power", "turbo", "off", "--json"]);
    }

    function cancelPending() {
        root.confirmOpen = false;
        root.confirmTitle = "";
        root.confirmMessage = "";
    }

    function setIdleTimeouts(dimSec, lockSec, dpmsSec) {
        _runOp([
            "python3", "-m", "backend.cli", "settings", "power", "idle",
            "--dim", String(Math.round(Number(dimSec))),
            "--lock", String(Math.round(Number(lockSec))),
            "--dpms", String(Math.round(Number(dpmsSec))),
            "--json"
        ]);
    }

    function _runOp(cmd) {
        root.busy = true;
        root.error = "";
        root.statusMessage = "";
        opProc.running = false;
        opProc.command = cmd;
        opProc.running = true;
    }

    Process {
        id: stateProc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.loading = false;
                var txt = this.text || "";
                if (txt.trim().length === 0) {
                    root.available = false;
                    root.error = "Empty response from power state probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root._applyState(data);
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse power state JSON: " + e.message;
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                var errTxt = (this.text || "").trim();
                if (errTxt.length > 0 && root.error.length === 0 && !root.available) {
                    root.error = errTxt;
                }
            }
        }
        onExited: function(exitCode) {
            root.loading = false;
            if (exitCode !== 0 && root.error.length === 0) {
                root.available = false;
                root.error = "Power probe exited with code " + exitCode;
            }
        }
    }

    Process {
        id: opProc
        workingDirectory: root.rootPath
        stdout: StdioCollector {
            onStreamFinished: {
                root.busy = false;
                var txt = this.text || "";
                if (txt.trim().length === 0) {
                    root.error = "Empty response from power operation.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    if (data.ok) {
                        root.statusMessage = String(data.message || "Power settings updated.");
                        root.error = "";
                    } else {
                        root.error = String(data.error || "Power operation failed.");
                    }
                    root.reload(true);
                } catch (e) {
                    root.error = "Failed to parse power op response: " + e.message;
                }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: {
                var errTxt = (this.text || "").trim();
                if (errTxt.length > 0 && root.error.length === 0) {
                    root.error = errTxt;
                }
            }
        }
        onExited: function(exitCode) {
            root.busy = false;
            if (exitCode !== 0 && root.error.length === 0) {
                root.error = "Power command exited with code " + exitCode;
            }
        }
    }
}
