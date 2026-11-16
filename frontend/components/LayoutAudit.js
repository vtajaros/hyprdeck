.pragma library

function _isActionBtn(it) {
    return !!(it && it.compact !== undefined && it.variant !== undefined && it.horizontalPadding !== undefined);
}

function _isTextItem(it) {
    return !!(it && it.contentWidth !== undefined && it.elide !== undefined && it.wrapMode !== undefined && it.maximumLineCount !== undefined);
}

function _isTextInputControl(it) {
    return !!(it && ((it.placeholderText !== undefined && it.background !== undefined) || (it.placeholder !== undefined && it.forceFocus !== undefined)));
}

function _itemLabel(it) {
    if (!it) return "Item";
    if (it.objectName && it.objectName.length > 0) return it.objectName;
    if (_isActionBtn(it)) {
        return "Button(\"" + String(it.text || "") + "\")";
    }
    if (it.text !== undefined && String(it.text).length > 0) {
        var s = String(it.text).replace(/\s+/g, " ").trim();
        if (s.length > 28) s = s.slice(0, 28) + "...";
        return "Text(\"" + s + "\")";
    }
    if (it.placeholderText !== undefined && String(it.placeholderText).length > 0) {
        return "TextField(\"" + String(it.placeholderText) + "\")";
    }
    return it.toString().split("(")[0];
}

function _hasHorizontalScrollerAncestor(pageRoot, it) {
    var p = it ? it.parent : null;
    while (p && p !== pageRoot) {
        if (p.objectName === "horizontalSafetyScroller" && pageRoot.width < 320) return true;
        if (p.clip === true && p.contentWidth !== undefined && p.width !== undefined && p.interactive !== undefined && p.contentWidth > p.width) return true;
        p = p.parent;
    }
    return false;
}

function _insideVerticalScrollView(pageRoot, it) {
    var p = it ? it.parent : null;
    while (p && p !== pageRoot) {
        if (p.contentWidth !== undefined && p.contentHeight !== undefined && p.interactive !== undefined) return true;
        p = p.parent;
    }
    return false;
}

function _clippedBoundsInScrollView(pageRoot, it, y1, y2) {
    var cy1 = y1;
    var cy2 = y2;
    var p = it ? it.parent : null;
    while (p && p !== pageRoot) {
        if (p.clip === true && p.contentWidth !== undefined && p.contentHeight !== undefined && p.interactive !== undefined) {
            var svPt = p.mapToItem(pageRoot, 0, 0);
            cy1 = Math.max(cy1, svPt.y);
            cy2 = Math.min(cy2, svPt.y + p.height);
        }
        p = p.parent;
    }
    return { y1: cy1, y2: cy2 };
}

function _isDescendant(anc, node) {
    var p = node ? node.parent : null;
    while (p) {
        if (p === anc) return true;
        p = p.parent;
    }
    return false;
}

function auditItem(pageRoot, textEnums) {
    if (!pageRoot) return { ok: false, error: "no active page", violations: [] };
    var noWrapVal = (textEnums && textEnums.noWrap !== undefined) ? textEnums.noWrap : 0;
    var elideNoneVal = (textEnums && textEnums.elideNone !== undefined) ? textEnums.elideNone : 3;
    var violations = [];
    var overlapLeaves = [];

    function _walk(node, path, inOpaque) {
        if (!node || !node.visible || node.opacity <= 0.01) return;
        if (node.width <= 0 && node.height <= 0 && node !== pageRoot) return;
        var label = _itemLabel(node);
        var curPath = path ? (path + "/" + label) : label;
        var isBtn = _isActionBtn(node);
        var isIn = _isTextInputControl(node);
        var isTxt = _isTextItem(node);
        var isOpaqueControl = isBtn || isIn;

        if (isOpaqueControl || isTxt) {
            var pt = node.mapToItem(pageRoot, 0, 0);
            var horizOk = _hasHorizontalScrollerAncestor(pageRoot, node);
            if (!horizOk && (pt.x < -2 || (pt.x + node.width) > (pageRoot.width + 2))) {
                violations.push({
                    type: "out_of_bounds",
                    item: label,
                    path: curPath,
                    detail: "x=" + Math.round(pt.x) + ".." + Math.round(pt.x + node.width) + " vs viewport 0.." + Math.round(pageRoot.width)
                });
            }
            if (!_insideVerticalScrollView(pageRoot, node) && (pt.y < -2 || (pt.y + node.height) > (pageRoot.height + 2))) {
                violations.push({
                    type: "out_of_bounds",
                    item: label,
                    path: curPath,
                    detail: "y=" + Math.round(pt.y) + ".." + Math.round(pt.y + node.height) + " vs viewport 0.." + Math.round(pageRoot.height)
                });
            }
            if (isOpaqueControl && (node.width < 28 || node.height < 24)) {
                violations.push({
                    type: "control_too_small",
                    item: label,
                    path: curPath,
                    detail: Math.round(node.width) + "x" + Math.round(node.height) + " < 28x24"
                });
            }
            if (isTxt && String(node.text || "").length > 0) {
                var isNoWrap = (node.wrapMode === noWrapVal);
                var isNoElide = (node.elide === elideNoneVal);
                var txtCw = node.contentWidth;
                var txtW = node.width;
                if (isNoWrap && isNoElide && txtCw > (txtW + 2)) {
                    violations.push({
                        type: "text_clipped",
                        item: label,
                        path: curPath,
                        detail: "contentWidth=" + Math.round(txtCw) + " > width=" + Math.round(txtW)
                    });
                } else if (!isNoElide && node.truncated === true && !(node.objectName && node.objectName.indexOf("elideOk") !== -1)) {
                    violations.push({
                        type: "text_clipped",
                        item: label,
                        path: curPath,
                        detail: "elided without elideOk mark (contentWidth=" + Math.round(txtCw) + " vs width=" + Math.round(txtW) + ")"
                    });
                }
            }
            if (!inOpaque && (isOpaqueControl || isTxt)) {
                var cb = _clippedBoundsInScrollView(pageRoot, node, pt.y, pt.y + node.height);
                if (cb.y2 - cb.y1 > 1) {
                    overlapLeaves.push({ node: node, label: label, path: curPath, x1: pt.x, y1: cb.y1, x2: pt.x + node.width, y2: cb.y2 });
                }
            }
        }

        var childOpaque = inOpaque || isOpaqueControl;
        var kids = node.children || [];
        for (var c = 0; c < kids.length; c++) {
            _walk(kids[c], curPath, childOpaque);
        }
    }

    _walk(pageRoot, "", false);

    for (var a = 0; a < overlapLeaves.length; a++) {
        var la = overlapLeaves[a];
        for (var b = a + 1; b < overlapLeaves.length; b++) {
            var lb = overlapLeaves[b];
            if (_isDescendant(la.node, lb.node) || _isDescendant(lb.node, la.node)) continue;
            var ox = Math.min(la.x2, lb.x2) - Math.max(la.x1, lb.x1);
            var oy = Math.min(la.y2, lb.y2) - Math.max(la.y1, lb.y1);
            if (ox > 2 && oy > 2) {
                violations.push({
                    type: "overlap",
                    item: la.label + " <-> " + lb.label,
                    path: la.path + " | " + lb.path,
                    detail: "overlap=" + Math.round(ox) + "x" + Math.round(oy)
                });
            }
        }
    }

    return { ok: true, count: violations.length, violations: violations };
}
