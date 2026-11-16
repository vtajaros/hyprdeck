pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "../theme"

Singleton {
    id: root

    property var binds: []
    property var conflicts: []
    property var disabledBinds: []
    property var diagnostics: []
    property var stats: ({})
    property var environment: ({})
    property bool loading: true
    property string error: ""
    property var categories: []
    property var submaps: []

    readonly property bool hasCompanionConf: {
        if (!root.diagnostics) return false;
        for (var i = 0; i < root.diagnostics.length; i++) {
            var d = root.diagnostics[i];
            if (d && (d.code === "conf_shadowed" || (d.message && d.message.indexOf("hyprland.conf") !== -1))) {
                return true;
            }
        }
        return false;
    }

    readonly property string rootPath: Deck.env("ROOT") || (Quickshell.env("HOME") + "/Shared/Projects/hyprdeck")
    readonly property string fixturePath: Deck.env("FIXTURE") || ""

    FileView {
        id: fixtureFile
        path: root.fixturePath
        blockLoading: true
        watchChanges: true
        onFileChanged: {
            if (root.fixturePath) root.loadFixture();
        }
    }

    Process {
        id: scanProc
        workingDirectory: root.rootPath
        command: ["python3", "-m", "backend.cli", "scan", "--compact"]
        stdout: StdioCollector {
            id: outCollector
            waitForEnd: true
        }
        stderr: StdioCollector {
            id: errCollector
            waitForEnd: true
        }
        onExited: (exitCode, exitStatus) => {
            root.handleScanFinished(exitCode, outCollector.text, errCollector.text);
        }
    }

    function reload() {
        root.error = "";
        root.loading = true;
        if (root.fixturePath) {
            loadFixture();
        } else {
            scanProc.running = false;
            scanProc.running = true;
        }
    }

    function loadFixture() {
        try {
            var raw = fixtureFile.text();
            if (!raw || !raw.trim()) {
                root.error = "Fixture file is empty or missing: " + root.fixturePath;
                root.loading = false;
                return;
            }
            var data = JSON.parse(raw);
            populateFromDoc(data);
        } catch (e) {
            root.error = "Failed to parse fixture: " + e.message;
            root.loading = false;
        }
    }

    function handleScanFinished(exitCode, stdoutText, stderrText) {
        if (exitCode !== 0) {
            var msg = (stderrText || "").trim();
            root.error = msg ? msg : ("Scan failed with exit code " + exitCode);
            root.loading = false;
            return;
        }
        try {
            var doc = JSON.parse(stdoutText || "{}");
            populateFromDoc(doc);
        } catch (e) {
            root.error = "Failed to parse scan output: " + e.message;
            root.loading = false;
        }
    }

    function populateFromDoc(doc) {
        root.error = "";
        root.binds = doc.binds || [];
        root.conflicts = doc.conflicts || [];
        root.disabledBinds = doc.disabled_binds || [];
        root.diagnostics = doc.diagnostics || [];
        root.stats = doc.stats || {};
        root.environment = doc.environment || {};

        // Compute categories with counts, sorted descending
        var catCounts = {};
        for (var i = 0; i < root.binds.length; i++) {
            var catName = root.binds[i].category || "Other";
            catCounts[catName] = (catCounts[catName] || 0) + 1;
        }
        var catList = [];
        for (var k in catCounts) {
            catList.push({ name: k, count: catCounts[k] });
        }
        catList.sort(function(a, b) {
            if (b.count !== a.count) return b.count - a.count;
            return a.name.localeCompare(b.name);
        });
        root.categories = catList;

        // Compute distinct non-empty submaps
        var submapSet = {};
        for (var j = 0; j < root.binds.length; j++) {
            var s = (root.binds[j].submap || "").trim();
            if (s.length > 0) submapSet[s] = true;
        }
        root.submaps = Object.keys(submapSet).sort();

        root.loading = false;
    }

    // Display helpers
    function friendlyKey(key) {
        if (!key) return "";
        var k = String(key);
        var lower = k.toLowerCase();
        var map = {
            "return": "Enter",
            "escape": "Esc",
            "space": "Space",
            "backspace": "Backspace",
            "delete": "Del",
            "insert": "Ins",
            "tab": "Tab",
            "grave": "`",
            "minus": "-",
            "equal": "=",
            "bracketleft": "[",
            "bracketright": "]",
            "backslash": "\\",
            "semicolon": ";",
            "apostrophe": "'",
            "comma": ",",
            "period": ".",
            "slash": "/",
            "left": "Left",
            "right": "Right",
            "up": "Up",
            "down": "Down",
            "prior": "PageUp",
            "next": "PageDown",
            "home": "Home",
            "end": "End",
            "print": "Print"
        };
        if (map[lower]) return map[lower];

        if (k.indexOf("KP_") === 0) {
            var num = k.substring(3);
            var kpMap = {
                "End": "KP 1", "Down": "KP 2", "Next": "KP 3",
                "Left": "KP 4", "Begin": "KP 5", "Right": "KP 6",
                "Home": "KP 7", "Up": "KP 8", "Prior": "KP 9",
                "Insert": "KP 0", "Delete": "KP ."
            };
            return kpMap[num] || ("KP " + num);
        }

        if (k.indexOf("mouse:") === 0) {
            var btn = k.substring(6);
            if (btn === "272") return "Mouse Left";
            if (btn === "273") return "Mouse Right";
            if (btn === "274") return "Mouse Middle";
            return "Mouse " + btn;
        }

        return k;
    }

    function shortcutParts(bind) {
        if (!bind) return [];
        var parts = [];
        if (bind.modifiers && bind.modifiers.length > 0) {
            for (var i = 0; i < bind.modifiers.length; i++) {
                parts.push(bind.modifiers[i]);
            }
        }
        parts.push(friendlyKey(bind.key));
        return parts;
    }

    function conflictShortcutParts(conflict) {
        if (!conflict) return [];
        var parts = [];
        if (conflict.modifiers && conflict.modifiers.length > 0) {
            for (var i = 0; i < conflict.modifiers.length; i++) {
                parts.push(conflict.modifiers[i]);
            }
        }
        if (conflict.key) {
            parts.push(friendlyKey(conflict.key));
        }
        return parts;
    }

    function parseShortcutString(str) {
        if (!str) return [];
        var raw = String(str).split("+");
        var res = [];
        for (var i = 0; i < raw.length; i++) {
            var p = raw[i].trim();
            if (p.length > 0) {
                res.push(friendlyKey(p));
            }
        }
        return res;
    }

    function conflictSearchQuery(conflict) {
        var parts = conflictShortcutParts(conflict);
        return parts.join(" ").toLowerCase();
    }

    function getBindById(id) {
        if (!id || !root.binds) return null;
        for (var i = 0; i < root.binds.length; i++) {
            if (root.binds[i] && root.binds[i].id === id) {
                return root.binds[i];
            }
        }
        return null;
    }

    function descriptionText(bind) {
        if (!bind) return "";
        if (bind.description_effective && bind.description_effective.text) {
            return bind.description_effective.text;
        }
        return bind.description || "";
    }

    function actionText(bind) {
        if (!bind || !bind.dispatcher) return "";
        var p = bind.dispatcher.path || "";
        var a = bind.dispatcher.arg_summary || "";
        return a ? (p + " " + a) : p;
    }

    function filter(searchText, category, submap) {
        var query = (searchText || "").trim().toLowerCase().replace(/\+/g, " ");
        var tokens = query ? query.split(/\s+/).filter(Boolean) : [];
        var result = [];

        for (var i = 0; i < root.binds.length; i++) {
            var b = root.binds[i];

            // Category filter
            if (category && category !== "All") {
                if ((b.category || "Other") !== category) {
                    continue;
                }
            }

            // Submap filter
            if (submap && submap !== "All") {
                if ((b.submap || "") !== submap) {
                    continue;
                }
            }

            // Text search tokens
            if (tokens.length > 0) {
                var desc = descriptionText(b).toLowerCase();
                var act = actionText(b).toLowerCase();
                var cat = (b.category || "").toLowerCase();
                var sc = shortcutParts(b).join(" ").toLowerCase();
                var sub = (b.submap || "").toLowerCase();
                var haystack = sc + " " + desc + " " + act + " " + cat + " " + sub;

                var matchesAll = true;
                for (var t = 0; t < tokens.length; t++) {
                    if (haystack.indexOf(tokens[t]) === -1) {
                        matchesAll = false;
                        break;
                    }
                }
                if (!matchesAll) continue;
            }

            result.push(b);
        }
        return result;
    }

    Component.onCompleted: {
        reload();
    }
}
