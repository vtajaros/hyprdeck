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

    Column {
        anchors.fill: parent
        anchors.margins: HKS.space24
        spacing: HKS.space12

        Row {
            width: parent.width
            spacing: HKS.space12

            Column {
                width: Math.max(200, parent.width - headerActions.width - HKS.space12)
                spacing: 4

                Text {
                    text: "System info"
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeTitle
                    font.weight: Font.Bold
                    color: HKS.fg
                }

                Text {
                    text: "Hardware, OS, and compositor summary (privacy-safe; IDs omitted)."
                    font.family: HKS.fontFamily
                    font.pixelSize: HKS.fontSizeSmall
                    color: HKS.muted
                }
            }

            Row {
                id: headerActions
                anchors.verticalCenter: parent.verticalCenter
                spacing: HKS.space8

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
        }

        Timer {
            id: copyResetTimer
            interval: 2000
            repeat: false
            onTriggered: root.copiedNotice = false
        }

        EmptyState {
            visible: !SystemService.loading && !SystemService.available
            width: parent.width
            height: 220
            icon: "󰋼"
            title: "System info unavailable"
            message: SystemService.error || "Unable to read system information."
        }

        Flickable {
            id: flick
            visible: SystemService.available
            width: parent.width
            height: Math.max(120, parent.height - y)
            clip: true
            contentWidth: width
            contentHeight: listCol.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: listCol
                width: flick.width
                spacing: 6

                Repeater {
                    model: root.infoRows
                    delegate: Rectangle {
                        id: infoCard
                        required property var modelData
                        width: listCol.width
                        height: rowContent.implicitHeight + 16
                        radius: HKS.radiusSmall
                        color: HKS.surface
                        border.width: 1
                        border.color: HKS.alpha(HKS.muted, 0.14)

                        Row {
                            id: rowContent
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 10
                            spacing: HKS.space12

                            Text {
                                width: 170
                                text: String(infoCard.modelData.label || "")
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: HKS.muted
                            }

                            Text {
                                width: Math.max(160, parent.width - 182)
                                text: String(infoCard.modelData.value || "")
                                font.family: HKS.fontFamily
                                font.pixelSize: HKS.fontSizeSmall
                                color: HKS.fg
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }
}
