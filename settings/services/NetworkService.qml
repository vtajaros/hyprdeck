pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../components"

Singleton {
    id: root

    readonly property string rootPath: Quickshell.env("HYPRDECK_ROOT") || Quickshell.env("HKS_ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")
    readonly property bool debugMode: Quickshell.env("HKS_SETTINGS_DEBUG") === "1"

    property bool available: false
    property var general: ({
        state: "unknown",
        connectivity: "none",
        wifi_hw_enabled: false,
        wifi_enabled: false,
        wwan_present: false,
        wwan_enabled: false,
        networking_enabled: false
    })
    property bool hasWifiDevice: false
    property var devices: []
    property var debugDevices: []
    property var connections: []
    property var wifiNetworks: []
    property var warnings: []
    property var safety: ({
        active_connection_count: 0,
        wifi_off_would_cut_session: false
    })
    property bool loading: true
    property bool busy: false
    property bool scanning: false
    property string error: ""
    property string statusMessage: ""
    property bool pollingEnabled: false
    property real lastScanEpochMs: 0
    property bool _autoRescanCheckedForShow: false

    onPollingEnabledChanged: {
        if (!root.pollingEnabled) {
            root._autoRescanCheckedForShow = false;
        } else {
            root.maybeAutoRescanOnShow();
        }
    }

    // Confirmation modal state
    property bool confirmOpen: false
    property string confirmTitle: ""
    property string confirmMessage: ""
    property var pendingAction: null

    // Ephemeral stdin buffer for joinWifi; cleared immediately on process start
    property string _ephemeralStdin: ""

    readonly property NetworkControlLogic logic: NetworkControlLogic {}

    Timer {
        id: pollTimer
        interval: 1000
        repeat: true
        running: root.pollingEnabled && !root.busy && !stateProc.running
        onTriggered: root.reload(true)
    }

    function _applyState(data) {
        root.available = !!data.available;
        root.general = data.general || root.general;
        root.hasWifiDevice = !!data.has_wifi_device;
        root.devices = data.devices || [];
        root.debugDevices = data.debug_devices || [];
        root.connections = data.connections || [];
        root.wifiNetworks = data.wifi_networks || [];
        root.warnings = data.warnings || [];
        root.safety = data.safety || root.safety;
        root.error = data.error ? String(data.error) : "";
    }

    function reload(silent) {
        if (stateProc.running) return;
        if (!silent) {
            root.loading = true;
            root.error = "";
        }
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "network", "state", "--json"];
        stateProc.running = true;
    }

    function requestWifiEnabled(enabled) {
        if (!enabled) {
            var msg = root.logic.destructiveConsequence("wifi_off", null, root.safety);
            if (msg.length > 0) {
                root.confirmTitle = "Turn off Wi-Fi?";
                root.confirmMessage = msg;
                root.pendingAction = { type: "wifi", value: false };
                root.confirmOpen = true;
                return;
            }
        }
        _runOp(["python3", "-m", "backend.cli", "settings", "network", "wifi", enabled ? "on" : "off", "--json"]);
    }

    function rescan() {
        if (root.busy || root.scanning || opProc.running) return;
        root.scanning = true;
        _runOp(["python3", "-m", "backend.cli", "settings", "network", "rescan", "--json"]);
    }

    function maybeAutoRescanOnShow() {
        if (root._autoRescanCheckedForShow || root.loading) return;
        root._autoRescanCheckedForShow = true;
        if (root.logic.shouldAutoRescanOnShow(
            root.pollingEnabled,
            root.available,
            root.hasWifiDevice,
            !!(root.general && root.general.wifi_enabled),
            root.busy,
            root.scanning,
            root.loading,
            (root.wifiNetworks || []).length,
            root.lastScanEpochMs,
            Date.now(),
            30000
        )) {
            root.rescan();
        }
    }

    function connectSaved(uuid) {
        _runOp(["python3", "-m", "backend.cli", "settings", "network", "connect", String(uuid), "--json"]);
    }

    function requestDisconnect(deviceObj) {
        if (!deviceObj) return;
        var msg = root.logic.destructiveConsequence("disconnect", deviceObj, root.safety);
        if (msg.length > 0) {
            root.confirmTitle = "Disconnect " + (deviceObj.name || "device") + "?";
            root.confirmMessage = msg;
            root.pendingAction = { type: "disconnect", device: String(deviceObj.name) };
            root.confirmOpen = true;
            return;
        }
        _runOp(["python3", "-m", "backend.cli", "settings", "network", "disconnect", String(deviceObj.name), "--json"]);
    }

    function requestForget(connObj) {
        if (!connObj) return;
        var msg = root.logic.destructiveConsequence("forget", connObj, root.safety);
        root.confirmTitle = "Forget " + (connObj.name || connObj.uuid) + "?";
        root.confirmMessage = msg;
        root.pendingAction = { type: "forget", uuid: String(connObj.uuid) };
        root.confirmOpen = true;
    }

    function confirmPending() {
        var act = root.pendingAction;
        root.confirmOpen = false;
        root.confirmTitle = "";
        root.confirmMessage = "";
        root.pendingAction = null;
        if (!act) return;
        if (act.type === "wifi") {
            _runOp(["python3", "-m", "backend.cli", "settings", "network", "wifi", act.value ? "on" : "off", "--json"]);
        } else if (act.type === "disconnect") {
            _runOp(["python3", "-m", "backend.cli", "settings", "network", "disconnect", String(act.device), "--confirm", "--json"]);
        } else if (act.type === "forget") {
            _runOp(["python3", "-m", "backend.cli", "settings", "network", "forget", String(act.uuid), "--confirm", "--json"]);
        }
    }

    function cancelPending() {
        root.confirmOpen = false;
        root.confirmTitle = "";
        root.confirmMessage = "";
        root.pendingAction = null;
    }

    function joinWifi(ssid, security, password) {
        var cmd = ["python3", "-m", "backend.cli", "settings", "network", "join", String(ssid), "--json"];
        if (security && String(security).length > 0) {
            cmd.push("--security", String(security));
        }
        // Never put password in argv; pass via stdin only and clear immediately
        root._ephemeralStdin = (password && String(password).length > 0) ? (String(password) + "\n") : "";
        _runOp(cmd);
    }

    function setAutoconnect(uuid, enabled) {
        _runOp(["python3", "-m", "backend.cli", "settings", "network", "autoconnect", String(uuid), enabled ? "on" : "off", "--json"]);
    }

    function setMetered(uuid, value) {
        _runOp(["python3", "-m", "backend.cli", "settings", "network", "metered", String(uuid), String(value), "--json"]);
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
                    root.error = "Empty response from NetworkManager state probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root._applyState(data);
                    if (root.pollingEnabled && !root._autoRescanCheckedForShow) {
                        root.maybeAutoRescanOnShow();
                    }
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse Network state JSON: " + e.message;
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
                root.error = "Network probe exited with code " + exitCode;
            }
        }
    }

    Process {
        id: opProc
        workingDirectory: root.rootPath
        stdinEnabled: true
        onStarted: {
            if (root._ephemeralStdin.length > 0) {
                opProc.write(root._ephemeralStdin);
                root._ephemeralStdin = "";
            }
        }
        stdout: StdioCollector {
            onStreamFinished: {
                var wasScanning = root.scanning;
                root.busy = false;
                root.scanning = false;
                root._ephemeralStdin = "";
                var txt = this.text || "";
                if (txt.trim().length === 0) {
                    root.error = "Empty response from network operation.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    if (data.ok) {
                        root.statusMessage = "Network updated.";
                        root.error = "";
                        if (wasScanning) {
                            root.lastScanEpochMs = Date.now();
                        }
                    } else {
                        root.error = String(data.error || "Network operation failed.");
                    }
                    root.reload(true);
                } catch (e) {
                    root.error = "Failed to parse network op response: " + e.message;
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
            root.scanning = false;
            root._ephemeralStdin = "";
            if (exitCode !== 0 && root.error.length === 0) {
                root.error = "Network command exited with code " + exitCode;
            }
        }
    }
}
