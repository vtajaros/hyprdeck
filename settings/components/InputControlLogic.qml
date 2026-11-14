import QtQuick

QtObject {
    id: root

    function _normList(arr, len) {
        var out = [];
        var src = arr || [];
        for (var i = 0; i < src.length; i++) {
            out.push(String(src[i] || "").trim());
        }
        while (len !== undefined && out.length < len) {
            out.push("");
        }
        return out;
    }

    function addLayout(layouts, variants, newLayout, newVariant) {
        var code = String(newLayout || "").trim();
        var lList = _normList(layouts);
        var vList = _normList(variants, lList.length);
        if (code.length === 0) {
            return { layouts: lList, variants: vList };
        }
        lList.push(code);
        vList.push(String(newVariant || "").trim());
        return { layouts: lList, variants: vList };
    }

    function moveLayout(layouts, variants, index, delta) {
        var lList = _normList(layouts);
        var vList = _normList(variants, lList.length);
        var target = index + delta;
        if (index < 0 || index >= lList.length || target < 0 || target >= lList.length) {
            return { layouts: lList, variants: vList };
        }
        var tmpL = lList[index];
        lList[index] = lList[target];
        lList[target] = tmpL;
        var tmpV = vList[index];
        vList[index] = vList[target];
        vList[target] = tmpV;
        return { layouts: lList, variants: vList };
    }

    function removeLayout(layouts, variants, index) {
        var lList = _normList(layouts);
        var vList = _normList(variants, lList.length);
        if (lList.length <= 1 || index < 0 || index >= lList.length) {
            return { layouts: lList, variants: vList };
        }
        lList.splice(index, 1);
        vList.splice(index, 1);
        return { layouts: lList, variants: vList };
    }

    function hasRiskyChanges(draftOptions, draftDevices, catalogOptions) {
        var devs = draftDevices || ({});
        if (Object.keys(devs).length > 0) {
            return true;
        }
        var opts = draftOptions || ({});
        var keys = Object.keys(opts);
        if (keys.length === 0) {
            return false;
        }
        var riskyMap = ({});
        var cat = catalogOptions || [];
        for (var i = 0; i < cat.length; i++) {
            var item = cat[i];
            if (item && item.id) {
                riskyMap[item.id] = !!item.risky;
            }
        }
        for (var j = 0; j < keys.length; j++) {
            if (riskyMap[keys[j]]) {
                return true;
            }
        }
        return false;
    }

    function modalActive(displayCountdown, inputCountdown) {
        return !!displayCountdown || !!inputCountdown;
    }

    function filterDevices(devices, showVirtual) {
        var list = devices || [];
        if (showVirtual) {
            return list.slice();
        }
        var out = [];
        for (var i = 0; i < list.length; i++) {
            var d = list[i];
            if (d && !d.virtual) {
                out.push(d);
            }
        }
        return out;
    }

    function _isPointerCategory(cat) {
        return cat === "mouse" || cat === "touchpad";
    }

    function canDisableDevice(devices, draftDevices, targetName) {
        var list = devices || [];
        var drafts = draftDevices || ({});
        var target = null;
        for (var i = 0; i < list.length; i++) {
            if (list[i] && list[i].name === targetName) {
                target = list[i];
                break;
            }
        }
        if (!target || target.virtual) {
            return true;
        }
        var wantKbd = target.category === "keyboard";
        var wantPtr = _isPointerCategory(target.category);
        if (!wantKbd && !wantPtr) {
            return true;
        }
        var enabledAfter = 0;
        for (var j = 0; j < list.length; j++) {
            var d = list[j];
            if (!d || d.virtual) continue;
            if (wantKbd && d.category !== "keyboard") continue;
            if (wantPtr && !_isPointerCategory(d.category)) continue;
            var ov = drafts[d.name];
            var en = (ov && ov.enabled !== undefined) ? !!ov.enabled : (d.enabled !== false);
            if (d.name === targetName) {
                en = false;
            }
            if (en) {
                enabledAfter++;
            }
        }
        return enabledAfter >= 1;
    }
}
