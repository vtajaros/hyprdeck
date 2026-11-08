pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool busy: false
    property bool active: false
    property string strategy: "passthrough"
    property bool limited: false
    property string error: ""
    property string submap: "default"

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
        interval: 5000
        repeat: false
        onTriggered: {
            if (root.busy) {
                proc.running = false;
                root.busy = false;
                root.error = "Recorder command timed out.";
                var cb = root._pendingCallback;
                root._pendingCallback = null;
                if (cb) {
                    cb(124, null, "Operation timed out.");
                }
            }
        }
    }

    function _exec(cmd, cb) {
        if (root.busy) {
            if (cb) cb(-1, null, "Recorder busy");
            return;
        }
        root.busy = true;
        root.error = "";
        root._pendingCallback = cb;
        proc.running = false;
        proc.command = cmd;
        proc.running = true;
        timeoutTimer.restart();
    }

    property var leaveHandler: null
    property var enterHandler: null
    property var statusHandler: null

    function enter(cb) {
        if (root.enterHandler) {
            root.enterHandler(cb);
            return;
        }
        _exec(["python3", "-m", "backend.cli", "recorder", "enter", "--json"], function(code, data, raw) {
            if (data && data.ok) {
                root.active = true;
                root.strategy = data.strategy || "passthrough";
                root.limited = (root.strategy === "limited");
                root.submap = data.submap || "";
                root.error = "";
            } else {
                root.active = false;
                root.strategy = "limited";
                root.limited = true;
                root.error = (data && data.reason) ? data.reason : (raw || "Failed to enter recorder submap");
            }
            if (cb) cb(data);
        });
    }

    function leave(cb) {
        if (root.leaveHandler) {
            root.leaveHandler(cb);
            return;
        }
        _exec(["python3", "-m", "backend.cli", "recorder", "leave", "--json"], function(code, data, raw) {
            root.active = false;
            root.submap = "default";
            if (!data || !data.ok) {
                root.error = (data && data.message) ? data.message : (raw || "Failed to leave recorder submap");
            }
            if (cb) cb(data);
        });
    }

    function heal(cb) {
        _exec(["python3", "-m", "backend.cli", "recorder", "heal", "--json"], function(code, data, raw) {
            if (data && data.ok) {
                root.active = false;
                root.submap = data.submap || "default";
            }
            if (cb) cb(data);
        });
    }

    function status(cb) {
        if (root.statusHandler) {
            root.statusHandler(cb);
            return;
        }
        _exec(["python3", "-m", "backend.cli", "recorder", "status", "--json"], function(code, data, raw) {
            if (data && data.ok) {
                root.submap = data.submap || "default";
                root.active = (root.submap === "hks_record");
            }
            if (cb) cb(data);
        });
    }
}
