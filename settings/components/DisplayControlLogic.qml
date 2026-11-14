import QtQuick

QtObject {
    id: root

    readonly property var transformLabels: [
        "Normal",
        "90°",
        "180°",
        "270°",
        "Flipped",
        "Flipped 90°",
        "Flipped 180°",
        "Flipped 270°"
    ]

    function isCleanScale(width, height, scale) {
        var w = Math.round(Number(width) || 0);
        var h = Math.round(Number(height) || 0);
        var s = Number(scale) || 0;
        if (w <= 0 || h <= 0 || s <= 0) {
            return false;
        }
        var denom = Math.round(s * 10000);
        if (denom <= 0) {
            return false;
        }
        return ((w * 10000) % denom === 0) && ((h * 10000) % denom === 0);
    }

    function scaleWarningText(width, height, scale) {
        return isCleanScale(width, height, scale) ? "" : "fractional: may blur";
    }

    function clampBrightness(pct) {
        var n = Math.round(Number(pct) || 0);
        return Math.max(5, Math.min(100, n));
    }

    function canDisableOutput(outputs, draftOutputs, targetName) {
        var list = outputs || [];
        var drafts = draftOutputs || ({});
        var enabledAfter = 0;
        var targetCurrentlyDisabled = false;
        for (var i = 0; i < list.length; i++) {
            var o = list[i];
            if (!o || !o.name) continue;
            var d = drafts[o.name];
            var isDisabled = (d && d.disabled !== undefined) ? !!d.disabled : !!o.disabled;
            if (o.name === targetName) {
                targetCurrentlyDisabled = isDisabled;
                isDisabled = true;
            }
            if (!isDisabled) {
                enabledAfter++;
            }
        }
        if (targetCurrentlyDisabled) {
            return true;
        }
        return enabledAfter >= 1;
    }

    function transformLabel(t) {
        var idx = Math.round(Number(t) || 0);
        if (idx < 0 || idx >= transformLabels.length) {
            return "Normal";
        }
        return transformLabels[idx];
    }
}
