pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

Singleton {
    id: root

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")
    readonly property bool debugMode: Deck.env("SETTINGS_DEBUG") === "1"

    property bool available: false
    property string defaultSink: ""
    property string defaultSource: ""
    property var outputs: []
    property var inputs: []
    property var streams: []
    property bool loading: true
    property bool busy: false
    property string error: ""
    property string statusMessage: ""
    property bool pollingEnabled: false

    Timer {
        id: pollTimer
        interval: 1000
        repeat: true
        running: root.pollingEnabled && !root.busy && !stateProc.running
        onTriggered: root.reload(true)
    }

    function _applyState(data) {
        root.available = !!data.available;
        root.defaultSink = String(data.default_sink || "");
        root.defaultSource = String(data.default_source || "");
        root.outputs = data.outputs || [];
        root.inputs = data.inputs || [];
        root.streams = data.streams || [];
        root.error = data.error ? String(data.error) : "";
    }

    function reload(silent) {
        if (stateProc.running) return;
        if (!silent) {
            root.loading = true;
            root.error = "";
        }
        stateProc.command = ["python3", "-m", "backend.cli", "settings", "audio", "state", "--json"];
        stateProc.running = true;
    }

    function setVolume(kind, name, pct) {
        var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
        var sub = (k === "source") ? "set-source-volume" : "set-sink-volume";
        var n = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)));
        root._runOp(["python3", "-m", "backend.cli", "settings", "audio", sub, String(name), String(n), "--json"]);
    }

    function setMute(kind, name, mode) {
        var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
        var sub = (k === "source") ? "set-source-mute" : "set-sink-mute";
        root._runOp(["python3", "-m", "backend.cli", "settings", "audio", sub, String(name), String(mode), "--json"]);
    }

    function setDefault(kind, name) {
        var k = (String(kind || "sink").toLowerCase() === "source") ? "source" : "sink";
        var sub = (k === "source") ? "set-default-source" : "set-default-sink";
        root._runOp(["python3", "-m", "backend.cli", "settings", "audio", sub, String(name), "--json"]);
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
                    root.error = "Empty response from audio state probe.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    root._applyState(data);
                } catch (e) {
                    root.available = false;
                    root.error = "Failed to parse audio state JSON: " + e.message;
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
                root.error = "Audio probe exited with code " + exitCode;
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
                    root.error = "Empty response from audio operation.";
                    return;
                }
                try {
                    var data = JSON.parse(txt);
                    if (data.ok) {
                        root.statusMessage = "Audio updated.";
                        root.error = "";
                    } else {
                        root.error = String(data.error || "Audio operation failed.");
                    }
                    root.reload(true);
                } catch (e) {
                    root.error = "Failed to parse audio op response: " + e.message;
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
                root.error = "Audio command exited with code " + exitCode;
            }
        }
    }
}
