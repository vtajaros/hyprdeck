import QtQuick

QtObject {
    id: root

    function _fileSortRank(fileName) {
        var name = String(fileName || "");
        if (name === "hyprland.lua") return 0;
        if (name === "hks-overrides.lua") return 1;
        if (name === "hypridle.conf") return 2;
        return 3;
    }

    function extractFileFilters(backups) {
        var items = Array.isArray(backups) ? backups : [];
        var seen = {};
        var names = [];
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            if (!it) continue;
            var name = String(it.file_name || "");
            if (name.length === 0 && it.original_path) {
                var parts = String(it.original_path).split("/");
                name = parts[parts.length - 1] || "";
            }
            if (name.length > 0 && !seen[name]) {
                seen[name] = true;
                names.push(name);
            }
        }
        names.sort(function(a, b) {
            var ra = root._fileSortRank(a);
            var rb = root._fileSortRank(b);
            if (ra !== rb) return ra - rb;
            return a < b ? -1 : (a > b ? 1 : 0);
        });
        return ["All"].concat(names);
    }

    function groupAndSortBackups(backups, fileFilter) {
        var items = Array.isArray(backups) ? backups : [];
        var filterStr = String(fileFilter || "All");
        var filtered = [];
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            if (!it) continue;
            var fname = String(it.file_name || "");
            if (fname.length === 0 && it.original_path) {
                var parts = String(it.original_path).split("/");
                fname = parts[parts.length - 1] || "";
            }
            if (filterStr !== "All" && fname !== filterStr) continue;
            filtered.push({
                id: String(it.id || ""),
                file_name: fname,
                original_path: String(it.original_path || ""),
                created_at: String(it.created_at || ""),
                sha256: String(it.sha256 || ""),
                size: Number(it.size || 0),
                available: !!it.available,
                is_current: !!it.is_current,
                reason: String(it.reason || "other"),
                has_sidecar: !!it.has_sidecar
            });
        }
        filtered.sort(function(a, b) {
            var ra = root._fileSortRank(a.file_name);
            var rb = root._fileSortRank(b.file_name);
            if (ra !== rb) return ra - rb;
            if (a.file_name !== b.file_name) {
                return a.file_name < b.file_name ? -1 : 1;
            }
            // Newest first within each file group
            if (a.created_at !== b.created_at) {
                return a.created_at > b.created_at ? -1 : 1;
            }
            return a.id > b.id ? -1 : (a.id < b.id ? 1 : 0);
        });
        return filtered;
    }

    function reasonLabel(reason) {
        var r = String(reason || "other");
        if (r === "pre-restore") return "Pre-restore";
        if (r === "edit") return "Edit";
        return "Other";
    }

    function canRestore(record, busy) {
        if (busy) return false;
        if (!record) return false;
        if (!record.available) return false;
        if (record.is_current) return false;
        return true;
    }

    function layoutMode(viewportWidth) {
        var w = Number(viewportWidth || 0);
        if (w >= 1200) return "split";
        if (w >= 700) return "stacked";
        return "compact";
    }

    function classifyDiffLine(line) {
        var s = String(line || "");
        if (s.indexOf("+++") === 0 || s.indexOf("---") === 0 || s.indexOf("diff ") === 0) return "meta";
        if (s.indexOf("@@") === 0) return "hunk";
        if (s.indexOf("+") === 0) return "add";
        if (s.indexOf("-") === 0) return "remove";
        return "context";
    }

    function formatBytes(bytes) {
        var b = Number(bytes || 0);
        if (b < 1024) return b + " B";
        if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
        return (b / 1048576).toFixed(1) + " MB";
    }
}
