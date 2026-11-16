import QtQuick

QtObject {
    id: root

    function applyScopeLabel(scope) {
        var s = String(scope || "").toLowerCase();
        if (s === "live") return "Applies live";
        if (s === "new_apps") return "Applies to new apps (restart apps to pick up)";
        if (s === "next_login") return "Requires re-login (overridden by GTK_THEME env)";
        return "";
    }

    function iconBadgeText(name) {
        return String(name || "") === "Papirus-Dynamic"
            ? "Follows wallpaper (recommended)"
            : "Resets on next wallpaper change";
    }

    function clampCursorSize(size) {
        var n = Math.round(Number(size) || 24);
        if (isNaN(n)) return 24;
        return Math.max(16, Math.min(64, n));
    }

    function hasConflict(conflicts, conflictId) {
        var list = conflicts || [];
        for (var i = 0; i < list.length; i++) {
            if (list[i] && list[i].id === conflictId) return true;
        }
        return false;
    }
}
