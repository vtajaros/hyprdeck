pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../components"
import "../theme"

Singleton {
    id: root

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")
    readonly property bool debugMode: Deck.env("SETTINGS_DEBUG") === "1"

    property bool available: false
    property bool noController: false
    property var controller: null
    property var rfkill: ({ available: false, soft_blocked: false, hard_blocked: false })
    property var devices: []
    property var safety: ({
        disconnecting_default_audio: false,
        default_audio_mac: "",
        default_audio_name: "",
        powering_off_disconnects: false,
        connected_count: 0,
        connected_names: []
    })
    property bool loading: true
    property bool busy: false
    property bool scanning: false
    property bool needsManualPairing: false
    property string manualPairMac: ""
    property string error: ""
    property string statusMessage: ""
    property bool pollingEnabled: false

    // Confirmation modal state for disruptive/destructive actions
    property bool confirmOpen: false
    property string confirmTitle: ""
    property string confirmMessage: ""
    property var pendingAction: null

    readonly property BluetoothControlLogic logic: BluetoothControlLogic {}

    Timer {
        id: pollTimer
        interval: 1000
        repeat: true
        running: root.pollingEnabled && !root.busy && !stateProc.running
        onTriggered: root.reload(true)
    }

    function _applyState(data) {
        root.available = !!data.available;
        root.noController = !!data.no_controller;
        root.controller = data.controller || null;
        root.rfkill = data.rfkill || ({ available: false, soft_blocked: false, hard_blocked: false });
        root.devices = data.devices || [];
        root.safety = data.safety || root.safety;
        root.scanning = !!(root.controller && root.controller.discovering);
        root.error = data.error ? String(data.error) : "";
    }

    function reload(silent) {
        if (stateProc.running) return;
        if (!silent) {
            root.loading = true;
            root.error = "";
        }
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "bluetooth", "state", "--json"];
        stateProc.running = true;
    }

    function requestPower(enabled) {
        if (!enabled) {
            var msg = root.logic.destructiveConsequence("power_off", null, root.safety);
            if (msg.length > 0) {
                root.confirmTitle = "Turn off Bluetooth?";
                root.confirmMessage = msg;
                root.pendingAction = { type: "power", value: false };
                root.confirmOpen = true;
                return;
            }
        }
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "power", enabled ? "on" : "off", "--json"]);
    }

    function setPairable(enabled) {
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "pairable", enabled ? "on" : "off", "--json"]);
    }

    function connect(mac) {
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "connect", String(mac), "--json"]);
    }

    function requestDisconnect(device) {
        if (!device) return;
        var msg = root.logic.destructiveConsequence("disconnect", device, root.safety);
        if (msg.length > 0) {
            root.confirmTitle = "Disconnect " + (device.alias || device.name || device.address) + "?";
            root.confirmMessage = msg;
            root.pendingAction = { type: "disconnect", mac: String(device.address) };
            root.confirmOpen = true;
            return;
        }
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "disconnect", String(device.address), "--json"]);
    }

    function setTrusted(mac, trusted) {
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", trusted ? "trust" : "untrust", String(mac), "--json"]);
    }

    function requestRemove(device) {
        if (!device) return;
        var msg = root.logic.destructiveConsequence("remove", device, root.safety);
        root.confirmTitle = "Remove " + (device.alias || device.name || device.address) + "?";
        root.confirmMessage = msg;
        root.pendingAction = { type: "remove", mac: String(device.address) };
        root.confirmOpen = true;
    }

    function confirmPending() {
        var act = root.pendingAction;
        root.confirmOpen = false;
        root.confirmTitle = "";
        root.confirmMessage = "";
        root.pendingAction = null;
        if (!act) return;
        if (act.type === "power") {
            _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "power", act.value ? "on" : "off", "--json"]);
        } else if (act.type === "disconnect") {
            _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "disconnect", String(act.mac), "--json"]);
        } else if (act.type === "remove") {
            _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "remove", String(act.mac), "--json"]);
        }
    }

    function cancelPending() {
        root.confirmOpen = false;
        root.confirmTitle = "";
        root.confirmMessage = "";
        root.pendingAction = null;
    }

    function startScan() {
        root.needsManualPairing = false;
        root.manualPairMac = "";
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "scan", "start", "--json"]);
    }

    function stopScan() {
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "scan", "stop", "--json"]);
    }

    function stopScanIfActive() {
        if (root.scanning && !root.busy) {
            stopScan();
        }
    }

    function pair(mac) {
        root.needsManualPairing = false;
        root.manualPairMac = String(mac);
        _runOp(["python3", "-m", "backend.cli", "settings", "bluetooth", "pair", String(mac), "--json"]);
    }

    function launchBlueman() {
        bluemanProc.running = false;
        bluemanProc.command = ["blueman-manager"];
        bluemanProc.running = true;
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
        id: bluemanProc
        workingDirectory: root.rootPath
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
                    root.error = "Empty response from Bluetooth state probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root._applyState(data);
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse Bluetooth state JSON: " + e.message;
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
                root.error = "Bluetooth probe exited with code " + exitCode;
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
                    root.error = "Empty response from Bluetooth operation.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    if (data.ok) {
                        root.statusMessage = "Bluetooth updated.";
                        root.error = "";
                        root.needsManualPairing = false;
                    } else {
                        root.error = String(data.error || "Bluetooth operation failed.");
                        root.needsManualPairing = !!data.needs_manual;
                    }
                    root.reload(true);
                } catch (e) {
                    root.error = "Failed to parse Bluetooth op response: " + e.message;
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
                root.error = "Bluetooth command exited with code " + exitCode;
            }
        }
    }
}
