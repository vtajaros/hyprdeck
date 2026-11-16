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

    function visibleThemeChips(items, current, showAll, maxOthers) {
        var list = items || [];
        var cap = (maxOthers !== undefined && maxOthers > 0) ? maxOthers : 8;
        if (showAll) {
            return list.slice();
        }
        var cur = String(current || "");
        var out = [];
        var seen = ({});
        if (cur.length > 0 && list.indexOf(cur) !== -1) {
            out.push(cur);
            seen[cur] = true;
        }
        var addedOthers = 0;
        for (var i = 0; i < list.length && addedOthers < cap; i++) {
            var item = list[i];
            if (seen[item]) continue;
            out.push(item);
            seen[item] = true;
            addedOthers++;
        }
        return out;
    }
}
