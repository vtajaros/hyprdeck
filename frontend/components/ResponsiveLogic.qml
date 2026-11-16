pragma Singleton
import QtQuick
import "../theme"

QtObject {
    id: root

    // Breakpoint thresholds with +/- 24px hysteresis band around 440, 680, 1000.
    function computeLayoutClass(width, prevClass) {
        var w = Number(width);
        if (isNaN(w) || w <= 0) {
            if (prevClass === "compact" || prevClass === "medium" || prevClass === "wide" || prevClass === "expanded")
                return prevClass;
            return "compact";
        }
        var hyst = 24;
        if (prevClass === "compact") {
            if (w < 440 + hyst)
                return "compact";
        } else if (prevClass === "medium") {
            if (w >= 440 - hyst && w < 680 + hyst)
                return "medium";
        } else if (prevClass === "wide") {
            if (w >= 680 - hyst && w < 1000 + hyst)
                return "wide";
        } else if (prevClass === "expanded") {
            if (w >= 1000 - hyst)
                return "expanded";
        }

        if (w < 440)
            return "compact";
        if (w < 680)
            return "medium";
        if (w < 1000)
            return "wide";
        return "expanded";
    }

    function isLayoutShort(height) {
        var h = Number(height);
        if (isNaN(h) || h <= 0)
            return false;
        return h < 640;
    }

    function sidebarModeForWindowWidth(winWidth) {
        var w = Number(winWidth);
        if (isNaN(w) || w <= 0)
            return "rail";
        if (w >= Deck.sidebarFullThreshold)
            return "full";
        if (w >= Deck.sidebarCompactThreshold)
            return "narrow";
        return "rail";
    }

    function sidebarWidthForMode(mode) {
        if (mode === "rail")
            return Deck.sidebarRailWidth;
        if (mode === "narrow")
            return Deck.sidebarNarrowWidth;
        return Deck.sidebarFullWidth;
    }

    function shouldWrapHeaderActions(availableWidth, titleWidth, actionsWidth, spacing) {
        var avail = Number(availableWidth);
        var actW = Number(actionsWidth);
        if (isNaN(actW) || actW <= 0)
            return false;
        if (isNaN(avail) || avail <= 0)
            return true;
        var gap = (spacing !== undefined && !isNaN(Number(spacing))) ? Number(spacing) : Deck.space12;
        var titleW = (!isNaN(Number(titleWidth))) ? Number(titleWidth) : 0;
        var minLeft = Math.max(titleW, 180);
        return (minLeft + gap + actW) > avail;
    }

    function shouldStackSettingRow(availableWidth, labelMinWidth, controlsWidth, spacing) {
        var avail = Number(availableWidth);
        var ctrlW = Number(controlsWidth);
        if (isNaN(ctrlW) || ctrlW <= 0)
            return false;
        if (isNaN(avail) || avail <= 0)
            return true;
        var gap = (spacing !== undefined && !isNaN(Number(spacing))) ? Number(spacing) : Deck.space12;
        var minLeft = (labelMinWidth !== undefined && !isNaN(Number(labelMinWidth))) ? Number(labelMinWidth) : 200;
        return (minLeft + gap + ctrlW) > avail;
    }

    function shouldWrapDeviceActions(availableWidth, infoMinWidth, actionsWidth, spacing) {
        var avail = Number(availableWidth);
        var actW = Number(actionsWidth);
        if (isNaN(actW) || actW <= 0)
            return false;
        if (isNaN(avail) || avail <= 0)
            return true;
        var gap = (spacing !== undefined && !isNaN(Number(spacing))) ? Number(spacing) : Deck.space12;
        var minLeft = (infoMinWidth !== undefined && !isNaN(Number(infoMinWidth))) ? Number(infoMinWidth) : 220;
        return (minLeft + gap + actW) > avail;
    }

    function keybindRowModeForClass(layoutClass) {
        if (layoutClass === "compact")
            return "stacked";
        if (layoutClass === "medium" || layoutClass === "cozy")
            return "two-line";
        return "columns";
    }

    function keybindActionsCollapsed(layoutClass) {
        return layoutClass === "compact" || layoutClass === "medium" || layoutClass === "cozy";
    }

    function clampDialogSize(preferredW, preferredH, viewportW, viewportH) {
        var pw = Number(preferredW) || 520;
        var ph = Number(preferredH) || 480;
        var vw = Number(viewportW) || pw;
        var vh = Number(viewportH) || ph;
        var maxW = Math.max(240, vw - 24);
        var maxH = Math.max(200, vh - 24);
        return {
            width: Math.min(pw, maxW),
            height: Math.min(ph, maxH)
        };
    }
}
