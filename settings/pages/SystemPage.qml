import QtQuick
import "../theme"
import "../shared_components"
import "../components"
import "../services"

Item {
    id: root

    PowerControlLogic {
        id: pwrLogic
    }

    property bool copiedNotice: false

    // Hidden TextEdit used for pure Qt clipboard copy without external processes
    TextEdit {
        id: copyBuffer
        visible: false
    }

    Timer {
        id: copyResetTimer
        interval: 2000
        repeat: false
        onTriggered: root.copiedNotice = false
    }

    readonly property var infoRows: {
        var inf = SystemService.info || ({});
        var rows = [];
        var pushRow = function(label, val) {
            if (val !== undefined && val !== null && String(val).length > 0) {
                rows.push({ label: label, value: String(val) });
            }
        };
        pushRow("Hostname", inf.hostname);
        pushRow("Operating System", inf.os_name);
        pushRow("Kernel", inf.kernel);
        pushRow("Hardware", inf.vendor_model);
        pushRow("Processor", inf.cpu_model ? (inf.cpu_model + (inf.cpu_cores ? (" (" + inf.cpu_cores + " threads)") : "")) : null);
        if (inf.ram_used && inf.ram_total) {
            pushRow("Memory", inf.ram_used + " / " + inf.ram_total);
        }
        if (inf.disk_root_used && inf.disk_root_total) {
            pushRow("Root Filesystem (/)", inf.disk_root_used + " / " + inf.disk_root_total + (inf.disk_root_percent ? (" (" + inf.disk_root_percent + ")") : ""));
        }
        pushRow("GPU", inf.gpu);
        pushRow("Uptime", inf.uptime);
        pushRow("Hyprland", inf.hyprland_version);
        pushRow("Quickshell", inf.quickshell_version);
        return rows;
    }

    PageViewport {
        id: viewport
        anchors.fill: parent

        header: PageHeader {
            title: "System Info"
            subtitle: "Hardware, OS, and compositor summary (privacy-safe; IDs omitted)."

            ActionButton {
                text: root.copiedNotice ? "Copied" : "Copy all"
                variant: "accent"
                compact: true
                enabled: SystemService.available && root.infoRows.length > 0
                onClicked: {
                    copyBuffer.text = pwrLogic.formatCopyAllText(SystemService.info);
                    copyBuffer.selectAll();
                    copyBuffer.copy();
                    root.copiedNotice = true;
                    copyResetTimer.restart();
                }
            }

            ActionButton {
                text: "Refresh"
                compact: true
                enabled: !SystemService.loading
                onClicked: SystemService.reload()
            }
        }

        EmptyState {
            visible: !SystemService.loading && !SystemService.available
            width: viewport.innerWidth
            height: 220
            icon: "󰋼"
            title: "System info unavailable"
            message: SystemService.error || "Unable to read system information."
        }

        SectionCard {
            visible: SystemService.available
            width: viewport.innerWidth
            cardPadding: Deck.space16
            spacing: 0

            Repeater {
                model: root.infoRows
                delegate: Item {
                    id: infoRow
                    required property var modelData
                    required property int index
                    readonly property real innerW: Math.max(0, width)
                    readonly property bool stacked: innerW < 440

                    width: parent.width
                    height: rowContent.implicitHeight + 16

                    Rectangle {
                        visible: infoRow.index > 0
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 1
                        color: Deck.alpha(Deck.muted, 0.14)
                    }

                    Item {
                        id: rowContent
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        implicitHeight: infoRow.stacked
                            ? (lblTxt.implicitHeight + 4 + valTxt.implicitHeight)
                            : Math.max(lblTxt.implicitHeight, valTxt.implicitHeight)
                        height: implicitHeight

                        Text {
                            id: lblTxt
                            x: 0
                            y: 0
                            width: infoRow.stacked ? infoRow.innerW : 170
                            text: String(infoRow.modelData.label || "")
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            font.weight: Font.DemiBold
                            color: Deck.muted
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            id: valTxt
                            x: infoRow.stacked ? 0 : 182
                            y: infoRow.stacked ? (lblTxt.implicitHeight + 4) : 0
                            width: infoRow.stacked ? infoRow.innerW : Math.max(0, infoRow.innerW - 182)
                            text: String(infoRow.modelData.value || "")
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.fg
                            wrapMode: Text.WrapAnywhere
                        }
                    }
                }
            }
        }
    }
}
