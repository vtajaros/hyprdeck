pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool loaded: false
    property bool loading: false
    property var catalog: []
    property var categories: []

    readonly property string rootPath: Quickshell.env("HYPRDECK_ROOT") || Quickshell.env("HKS_ROOT") || "."

    Process {
        id: proc
        workingDirectory: root.rootPath
        command: ["python3", "-m", "backend.cli", "dispatchers", "--json"]
        stdout: StdioCollector {
            id: outCollector
            waitForEnd: true
        }
        onExited: (exitCode, exitStatus) => {
            root.loading = false;
            if (exitCode === 0) {
                var outStr = outCollector.text || "";
                try {
                    var parsed = JSON.parse(outStr);
                    if (parsed && parsed.dispatchers) {
                        root.catalog = parsed.dispatchers;
                        var cats = [];
                        for (var i = 0; i < parsed.dispatchers.length; i++) {
                            var item = parsed.dispatchers[i];
                            if (item.category && cats.indexOf(item.category) === -1) {
                                cats.push(item.category);
                            }
                        }
                        root.categories = cats;
                        root.loaded = true;
                    }
                } catch (e) {
                    root.loaded = false;
                }
            }
        }
    }

    Component.onCompleted: {
        load();
    }

    function load() {
        if (root.loading || root.loaded) return;
        root.loading = true;
        proc.running = true;
    }

    function getDispatcher(id) {
        if (!id) return null;
        var clean = id.trim().toLowerCase();
        for (var i = 0; i < root.catalog.length; i++) {
            var item = root.catalog[i];
            if (item.id && item.id.toLowerCase() === clean) {
                return item;
            }
            if (item.hyprlang_name && item.hyprlang_name.toLowerCase() === clean) {
                return item;
            }
        }
        // Aliases
        if (clean === "killactive" || clean === "close") {
            return getDispatcher("window.close");
        }
        if (clean === "exec") {
            return getDispatcher("exec_cmd");
        }
        if (clean === "float") {
            return getDispatcher("togglefloating");
        }
        if (clean === "focus") {
            return getDispatcher("movefocus");
        }
        return null;
    }
}
