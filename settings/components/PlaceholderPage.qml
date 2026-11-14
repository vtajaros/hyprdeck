import QtQuick
import "../theme"

Item {
    id: root

    property string title: ""
    property string icon: ""
    property string summary: "Planned for a future milestone."

    Column {
        anchors.centerIn: parent
        spacing: HKS.space12
        width: 420

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.icon
            font.family: HKS.fontFamily
            font.pixelSize: 36
            color: HKS.muted
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.title
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeTitle
            font.weight: Font.Bold
            color: HKS.fg
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: soonTxt.implicitWidth + 16
            height: 22
            radius: 6
            color: HKS.elevated
            border.width: 1
            border.color: HKS.alpha(HKS.muted, 0.25)
            Text {
                id: soonTxt
                anchors.centerIn: parent
                text: "Coming soon"
                font.family: HKS.fontFamily
                font.pixelSize: HKS.fontSizeSmall
                color: HKS.muted
            }
        }

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.summary
            font.family: HKS.fontFamily
            font.pixelSize: HKS.fontSizeSmall
            color: HKS.muted
            wrapMode: Text.WordWrap
        }
    }
}
