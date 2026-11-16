import QtQuick
import "../theme"
import "../services"

Item {
    id: root

    property var parts: []
    property bool active: false

    clip: true
    implicitHeight: 24
    implicitWidth: totalNaturalWidth

    readonly property real defaultSpacing: 6
    readonly property real minSpacing: 1.5

    // Normalize parts: supports list of strings or single string representation
    readonly property var keyList: {
        if (!root.parts) return [];
        if (typeof root.parts === "string") {
            return KeybindData.parseShortcutString(root.parts);
        }
        if (Array.isArray(root.parts)) {
            var res = [];
            for (var i = 0; i < root.parts.length; i++) {
                var k = root.parts[i];
                if (k !== null && k !== undefined && String(k).trim().length > 0) {
                    res.push(String(k).trim());
                }
            }
            return res;
        }
        return [];
    }

    readonly property int keyCount: keyList.length
    readonly property int sepCount: Math.max(0, keyCount - 1)

    // Flat model: keycaps interleaved with '+' separators
    // Single-key shortcuts have sepCount === 0 and produce no '+'
    readonly property var flatModel: {
        var list = root.keyList;
        if (!list || list.length === 0) return [];
        var res = [];
        for (var i = 0; i < list.length; i++) {
            if (i > 0) {
                res.push({ isKey: false, text: "+" });
            }
            res.push({ isKey: true, text: list[i], keyIndex: i });
        }
        return res;
    }

    function estimateKeyWidth(key) {
        if (!key) return 26;
        var textWidth = key.length * 6.6;
        return Math.min(280, Math.max(26, Math.round(textWidth + 14)));
    }

    readonly property real totalNaturalKeyWidth: {
        var sum = 0;
        for (var i = 0; i < root.keyList.length; i++) {
            sum += estimateKeyWidth(root.keyList[i]);
        }
        return sum;
    }

    readonly property real totalNaturalWidth: {
        if (keyCount === 0) return 0;
        return totalNaturalKeyWidth + (sepCount * 7) + (sepCount * 2 * defaultSpacing);
    }

    readonly property real availWidth: {
        if (root.width > 0) return root.width;
        return totalNaturalWidth;
    }

    readonly property real excessWidth: {
        if (availWidth <= 0 || totalNaturalWidth <= availWidth) return 0;
        return totalNaturalWidth - availWidth;
    }

    // Spacing between keycap and "+" (reduced first if excess exists)
    readonly property real currentSpacing: {
        if (sepCount === 0 || excessWidth <= 0) return defaultSpacing;
        var maxSpacingSaving = sepCount * 2 * (defaultSpacing - minSpacing);
        if (excessWidth <= maxSpacingSaving) {
            return defaultSpacing - (excessWidth / (sepCount * 2));
        }
        return minSpacing;
    }

    // Remaining excess after reducing separator spacing to minSpacing
    readonly property real remainingExcess: {
        if (sepCount === 0) return excessWidth;
        var maxSpacingSaving = sepCount * 2 * (defaultSpacing - minSpacing);
        return Math.max(0, excessWidth - maxSpacingSaving);
    }

    function keyWidth(index, text) {
        var natural = estimateKeyWidth(text);
        if (remainingExcess <= 0) {
            return natural;
        }
        // If there is excess to absorb, reduce the width of the last key (main key) first,
        // letting Keycap elide with Text.ElideRight
        if (index === keyList.length - 1 && keyList.length > 1) {
            return Math.max(30, natural - remainingExcess);
        }
        if (keyList.length === 1) {
            return Math.max(30, Math.min(natural, availWidth));
        }
        return natural;
    }

    Row {
        id: keysRow
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        spacing: root.currentSpacing

        Repeater {
            model: root.flatModel
            delegate: Item {
                anchors.verticalCenter: parent.verticalCenter
                width: modelData.isKey ? cap.width : plusText.implicitWidth
                height: 24

                Keycap {
                    id: cap
                    visible: modelData.isKey
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.isKey ? modelData.text : ""
                    active: root.active
                    width: modelData.isKey ? root.keyWidth(modelData.keyIndex, modelData.text) : implicitWidth
                }

                Text {
                    id: plusText
                    visible: !modelData.isKey
                    anchors.centerIn: parent
                    text: "+"
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    font.weight: Font.DemiBold
                    color: Deck.muted
                }
            }
        }
    }
}
