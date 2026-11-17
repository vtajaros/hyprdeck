import QtQuick
import "../theme"
import "../shared_components"
import "../services"

Item {
    id: root

    property string selectedCategory: "All"
    property string searchQuery: ""
    property bool showAdvanced: false

    // Dropdown menu state (compact "Open With"-style menu anchored to button)
    property var dropdownAssoc: null
    property real dropdownAnchorX: 0
    property real dropdownAnchorY: 0
    property real dropdownAnchorBottomY: 0

    // "Other Applications..." searchable modal state
    property var pickerAssoc: null
    property string pickerSearch: ""

    function _asList(val) {
        if (!val || val.length === undefined) return [];
        var out = [];
        for (var i = 0; i < val.length; i++) {
            out.push(val[i]);
        }
        return out;
    }

    function categoryIcon(cat) {
        if (cat === "Web") return "󰖟";
        if (cat === "Files") return "󰉋";
        if (cat === "Documents") return "󰈙";
        if (cat === "Images") return "󰋩";
        if (cat === "Video") return "󰕧";
        if (cat === "Audio") return "󰎈";
        if (cat === "Text") return "󰈚";
        if (cat === "Archives") return "󰀼";
        return "󰀻";
    }

    function appIcon(desktopId, appName, fallbackCategory) {
        var s = (String(desktopId || "") + " " + String(appName || "")).toLowerCase();
        if (s.indexOf("firefox") !== -1) return "󰈹";
        if (s.indexOf("brave") !== -1 || s.indexOf("chromium") !== -1 || s.indexOf("chrome") !== -1 || s.indexOf("vivaldi") !== -1) return "󰊯";
        if (s.indexOf("thunderbird") !== -1 || s.indexOf("geary") !== -1 || s.indexOf("mail") !== -1) return "󰇮";
        if (s.indexOf("thunar") !== -1 || s.indexOf("dolphin") !== -1 || s.indexOf("nautilus") !== -1 || s.indexOf("nemo") !== -1 || s.indexOf("pcmanfm") !== -1) return "󰉋";
        if (s.indexOf("kitty") !== -1 || s.indexOf("alacritty") !== -1 || s.indexOf("wezterm") !== -1 || s.indexOf("foot") !== -1 || s.indexOf("konsole") !== -1 || s.indexOf("terminal") !== -1) return "󰆍";
        if (s.indexOf("evince") !== -1 || s.indexOf("zathura") !== -1 || s.indexOf("okular") !== -1 || s.indexOf("document viewer") !== -1) return "󰈙";
        if (s.indexOf("mpv") !== -1 || s.indexOf("vlc") !== -1 || s.indexOf("totem") !== -1) return "󰕧";
        if (s.indexOf("audacity") !== -1 || s.indexOf("spotify") !== -1 || s.indexOf("rhythmbox") !== -1 || s.indexOf("elisa") !== -1) return "󰎈";
        if (s.indexOf("gimp") !== -1 || s.indexOf("loupe") !== -1 || s.indexOf("eog") !== -1 || s.indexOf("imv") !== -1 || s.indexOf("feh") !== -1 || s.indexOf("krita") !== -1 || s.indexOf("image viewer") !== -1) return "󰋩";
        if (s.indexOf("code") !== -1 || s.indexOf("antigravity") !== -1 || s.indexOf("nvim") !== -1 || s.indexOf("vim") !== -1 || s.indexOf("gedit") !== -1 || s.indexOf("mousepad") !== -1 || s.indexOf("kate") !== -1 || s.indexOf("text editor") !== -1) return "󰨞";
        if (s.indexOf("ark") !== -1 || s.indexOf("file-roller") !== -1 || s.indexOf("xarchiver") !== -1) return "󰀼";
        return root.categoryIcon(fallbackCategory || "Other");
    }

    function handleEscape() {
        if (root.pickerAssoc !== null) {
            root.closePicker();
            return true;
        }
        if (root.dropdownAssoc !== null) {
            root.closeDropdown();
            return true;
        }
        return false;
    }

    function _matchesFilter(item, cat, q) {
        if (!item) return false;
        if (cat !== "All" && item.category !== cat) return false;
        if (q.length > 0) {
            var exts = root._asList(item.extensions).join(" ");
            var cands = root._asList(item.candidates)
                .map(function(c) { return (c.name || "") + " " + (c.desktop_id || ""); })
                .join(" ");
            var hay = [
                item.mime_type || "",
                item.label || "",
                item.category || "",
                item.default_app_name || "",
                item.default_desktop_id || "",
                exts,
                cands
            ].join(" ").toLowerCase();
            if (hay.indexOf(q) === -1) return false;
        }
        return true;
    }

    readonly property var essentialAssociations: {
        var list = root._asList(DefaultAppsService.associations);
        var cat = root.selectedCategory;
        var q = root.searchQuery.trim().toLowerCase();
        var out = [];
        for (var i = 0; i < list.length; i++) {
            var item = list[i];
            if (item && item.essential && root._matchesFilter(item, cat, q)) {
                out.push(item);
            }
        }
        return out;
    }

    readonly property var advancedAssociations: {
        var list = root._asList(DefaultAppsService.associations);
        var cat = root.selectedCategory;
        var q = root.searchQuery.trim().toLowerCase();
        var out = [];
        for (var i = 0; i < list.length; i++) {
            var item = list[i];
            if (item && !item.essential && root._matchesFilter(item, cat, q)) {
                out.push(item);
            }
        }
        return out;
    }

    readonly property bool advancedExpanded: root.showAdvanced
        || root.searchQuery.trim().length > 0
        || (root.selectedCategory !== "All" && root.essentialAssociations.length === 0)

    readonly property var dropdownCandidates: {
        if (!root.dropdownAssoc) return [];
        return root._asList(root.dropdownAssoc.candidates);
    }

    readonly property var pickerCompatibleApps: {
        if (!root.pickerAssoc) return [];
        var cands = root._asList(root.pickerAssoc.candidates);
        var q = root.pickerSearch.trim().toLowerCase();
        if (q.length === 0) return cands;
        return cands.filter(function(c) {
            return ((c.name || "") + " " + (c.desktop_id || "")).toLowerCase().indexOf(q) !== -1;
        });
    }

    readonly property var pickerOtherApps: {
        if (!root.pickerAssoc) return [];
        var cands = root._asList(root.pickerAssoc.candidates);
        var candSet = {};
        for (var i = 0; i < cands.length; i++) {
            if (cands[i] && cands[i].desktop_id) {
                candSet[cands[i].desktop_id] = true;
            }
        }
        var all = root._asList(DefaultAppsService.installedApps);
        var q = root.pickerSearch.trim().toLowerCase();
        var out = [];
        for (var j = 0; j < all.length; j++) {
            var app = all[j];
            if (!app || candSet[app.desktop_id]) continue;
            if (q.length > 0) {
                var hay = ((app.name || "") + " " + (app.desktop_id || "")).toLowerCase();
                if (hay.indexOf(q) === -1) continue;
            }
            out.push(app);
        }
        return out;
    }

    function openDropdown(assoc, btnItem) {
        if (root.dropdownAssoc && root.dropdownAssoc.mime_type === assoc.mime_type) {
            root.closeDropdown();
            return;
        }
        var pt = btnItem.mapToItem(root, btnItem.width, btnItem.height);
        var topPt = btnItem.mapToItem(root, btnItem.width, 0);
        root.dropdownAnchorX = pt.x;
        root.dropdownAnchorY = pt.y + 4;
        root.dropdownAnchorBottomY = topPt.y - 4;
        root.dropdownAssoc = assoc;
    }

    function closeDropdown() {
        root.dropdownAssoc = null;
    }

    function openPicker(assoc) {
        root.closeDropdown();
        root.pickerSearch = "";
        root.pickerAssoc = assoc;
    }

    function closePicker() {
        root.pickerAssoc = null;
        root.pickerSearch = "";
    }

    PageViewport {
        id: viewport
        anchors.fill: parent
        allowTwoColumns: true

        header: PageHeader {
            title: "Default Applications"
            subtitle: "Choose which applications open common file types and URL schemes (changes apply immediately)."

            ActionButton {
                text: "Refresh"
                compact: true
                enabled: !DefaultAppsService.loading && !DefaultAppsService.busy
                onClicked: DefaultAppsService.reload()
            }
        }

        // Error banner
        Rectangle {
            visible: DefaultAppsService.error.length > 0
            width: viewport.innerWidth
            height: errTxt.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.critical, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.critical, 0.5)

            Text {
                id: errTxt
                anchors.fill: parent
                anchors.margins: 8
                text: DefaultAppsService.error
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.critical
                wrapMode: Text.WordWrap
            }
        }

        // Status banner
        Rectangle {
            visible: DefaultAppsService.statusMessage.length > 0 && DefaultAppsService.error.length === 0
            width: viewport.innerWidth
            height: stTxt.implicitHeight + 16
            radius: Deck.radiusSmall
            color: Deck.alpha(Deck.accent, 0.14)
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.45)

            Text {
                id: stTxt
                anchors.fill: parent
                anchors.margins: 8
                text: DefaultAppsService.statusMessage
                font.family: Deck.fontFamily
                font.pixelSize: Deck.fontSizeSmall
                color: Deck.accent
                wrapMode: Text.WordWrap
            }
        }

        // Search + Category filter card
        SectionCard {
            width: viewport.innerWidth
            cardPadding: Deck.space16
            spacing: Deck.space12

            Row {
                width: parent.width
                spacing: Deck.space12

                SearchField {
                    id: appSearch
                    width: Math.max(180, parent.width - summaryTxt.implicitWidth - Deck.space12)
                    height: 34
                    placeholder: "Search file extension (.pdf, .mp4), MIME type, or app..."
                    onTextChanged: root.searchQuery = text
                }

                Text {
                    id: summaryTxt
                    anchors.verticalCenter: parent.verticalCenter
                    text: DefaultAppsService.loading
                        ? "Loading..."
                        : (root.essentialAssociations.length + " common  •  " + root.advancedAssociations.length + " advanced")
                    font.family: Deck.fontFamily
                    font.pixelSize: Deck.fontSizeSmall
                    color: Deck.muted
                }
            }

            ChipFlow {
                width: parent.width
                spacing: 6

                Repeater {
                    model: DefaultAppsService.categories || ["All"]
                    delegate: ActionButton {
                        required property string modelData
                        text: modelData
                        compact: true
                        variant: root.selectedCategory === modelData ? "primary" : "default"
                        onClicked: root.selectedCategory = modelData
                    }
                }
            }
        }

        EmptyState {
            visible: !DefaultAppsService.loading
                && root.essentialAssociations.length === 0
                && root.advancedAssociations.length === 0
            width: viewport.innerWidth
            height: 200
            icon: "󰀻"
            title: "No matching file associations"
            message: root.searchQuery.trim().length > 0
                ? "Try searching another extension, MIME type, or application name."
                : "No file type associations were found in this category."
        }

        // Common / Essential File Types
        Flow {
            visible: root.essentialAssociations.length > 0
            width: viewport.innerWidth
            spacing: viewport.columnSpacing

            Repeater {
                model: root.essentialAssociations
                delegate: SectionCard {
                    id: essCard
                    required property var modelData
                    width: viewport.twoColumnCardWidth
                    cardPadding: Deck.space12
                    spacing: Deck.space8

                    readonly property var extList: root._asList(modelData.extensions)
                    readonly property bool hasDefault: !!(modelData.default_desktop_id && modelData.default_desktop_id.length > 0)

                    Item {
                        id: essRow
                        width: parent.width
                        readonly property bool narrow: width < 360
                        implicitHeight: narrow
                            ? (essLeft.implicitHeight + Deck.space8 + essPickerBtn.height)
                            : Math.max(essLeft.implicitHeight, essPickerBtn.height)
                        height: implicitHeight

                        Row {
                            id: essLeft
                            x: 0
                            y: 0
                            width: essRow.narrow
                                ? essRow.width
                                : Math.max(0, essRow.width - essPickerBtn.width - Deck.space12)
                            spacing: Deck.space12

                            Rectangle {
                                width: 34
                                height: 34
                                radius: Deck.radiusSmall
                                anchors.verticalCenter: parent.verticalCenter
                                color: Deck.alpha(Deck.accent, 0.14)
                                border.width: 1
                                border.color: Deck.alpha(Deck.accent, 0.28)

                                Text {
                                    anchors.centerIn: parent
                                    text: root.categoryIcon(essCard.modelData.category || "Other")
                                    font.family: Deck.fontFamily
                                    font.pixelSize: 16
                                    color: Deck.accent
                                }
                            }

                            Column {
                                width: Math.max(0, parent.width - 34 - Deck.space12)
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: essCard.modelData.label || essCard.modelData.mime_type
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    font.weight: Font.DemiBold
                                    color: Deck.fg
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: essCard.modelData.mime_type
                                        + (essCard.extList.length > 0 ? ("  •  " + essCard.extList.join(" ")) : "")
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    color: Deck.muted
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        ActionButton {
                            id: essPickerBtn
                            x: essRow.narrow ? 0 : Math.max(0, essRow.width - width)
                            y: essRow.narrow ? (essLeft.implicitHeight + Deck.space8) : 0
                            compact: true
                            variant: essCard.hasDefault ? "primary" : "default"
                            enabled: !DefaultAppsService.busy
                            text: (essCard.hasDefault
                                ? (root.appIcon(essCard.modelData.default_desktop_id, essCard.modelData.default_app_name, essCard.modelData.category)
                                    + "  " + (essCard.modelData.default_app_name || essCard.modelData.default_desktop_id))
                                : "Choose app") + "  ▾"
                            onClicked: root.openDropdown(essCard.modelData, essPickerBtn)
                        }
                    }
                }
            }
        }

        // Advanced File Associations Toggle Card
        SectionCard {
            visible: root.advancedAssociations.length > 0
            width: viewport.innerWidth
            cardPadding: Deck.space12
            spacing: Deck.space8

            Item {
                width: parent.width
                implicitHeight: Math.max(advHdrCol.implicitHeight, advToggleBtn.height)
                height: implicitHeight

                Column {
                    id: advHdrCol
                    anchors.left: parent.left
                    anchors.right: advToggleBtn.left
                    anchors.rightMargin: Deck.space12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        width: parent.width
                        text: "Advanced File Associations (" + root.advancedAssociations.length + ")"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSize
                        font.weight: Font.DemiBold
                        color: Deck.fg
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: "Additional MIME types and system file associations."
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        color: Deck.muted
                        elide: Text.ElideRight
                    }
                }

                ActionButton {
                    id: advToggleBtn
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    compact: true
                    text: root.advancedExpanded ? "Hide Advanced" : "Show Advanced"
                    onClicked: root.showAdvanced = !root.showAdvanced
                }
            }
        }

        // Advanced File Types (only instantiated when expanded)
        Flow {
            visible: root.advancedExpanded && root.advancedAssociations.length > 0
            width: viewport.innerWidth
            spacing: viewport.columnSpacing

            Repeater {
                model: root.advancedExpanded ? root.advancedAssociations : []
                delegate: SectionCard {
                    id: advCard
                    required property var modelData
                    width: viewport.twoColumnCardWidth
                    cardPadding: Deck.space12
                    spacing: Deck.space8

                    readonly property var extList: root._asList(modelData.extensions)
                    readonly property bool hasDefault: !!(modelData.default_desktop_id && modelData.default_desktop_id.length > 0)

                    Item {
                        id: advRow
                        width: parent.width
                        readonly property bool narrow: width < 360
                        implicitHeight: narrow
                            ? (advLeft.implicitHeight + Deck.space8 + advPickerBtn.height)
                            : Math.max(advLeft.implicitHeight, advPickerBtn.height)
                        height: implicitHeight

                        Row {
                            id: advLeft
                            x: 0
                            y: 0
                            width: advRow.narrow
                                ? advRow.width
                                : Math.max(0, advRow.width - advPickerBtn.width - Deck.space12)
                            spacing: Deck.space12

                            Rectangle {
                                width: 34
                                height: 34
                                radius: Deck.radiusSmall
                                anchors.verticalCenter: parent.verticalCenter
                                color: Deck.alpha(Deck.accent, 0.14)
                                border.width: 1
                                border.color: Deck.alpha(Deck.accent, 0.28)

                                Text {
                                    anchors.centerIn: parent
                                    text: root.categoryIcon(advCard.modelData.category || "Other")
                                    font.family: Deck.fontFamily
                                    font.pixelSize: 16
                                    color: Deck.accent
                                }
                            }

                            Column {
                                width: Math.max(0, parent.width - 34 - Deck.space12)
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: advCard.modelData.label || advCard.modelData.mime_type
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    font.weight: Font.DemiBold
                                    color: Deck.fg
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: advCard.modelData.mime_type
                                        + (advCard.extList.length > 0 ? ("  •  " + advCard.extList.join(" ")) : "")
                                        + "  •  " + (advCard.modelData.category || "Other")
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    color: Deck.muted
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        ActionButton {
                            id: advPickerBtn
                            x: advRow.narrow ? 0 : Math.max(0, advRow.width - width)
                            y: advRow.narrow ? (advLeft.implicitHeight + Deck.space8) : 0
                            compact: true
                            variant: advCard.hasDefault ? "primary" : "default"
                            enabled: !DefaultAppsService.busy
                            text: (advCard.hasDefault
                                ? (root.appIcon(advCard.modelData.default_desktop_id, advCard.modelData.default_app_name, advCard.modelData.category)
                                    + "  " + (advCard.modelData.default_app_name || advCard.modelData.default_desktop_id))
                                : "Choose app") + "  ▾"
                            onClicked: root.openDropdown(advCard.modelData, advPickerBtn)
                        }
                    }
                }
            }
        }
    }

    // Compact "Open With"-style Dropdown Menu
    Item {
        id: dropdownLayer
        anchors.fill: parent
        visible: root.dropdownAssoc !== null
        z: 90

        MouseArea {
            anchors.fill: parent
            onClicked: root.closeDropdown()
        }

        Rectangle {
            id: dropdownMenu
            width: Math.min(280, Math.max(200, root.width - 32))
            height: Math.min(340, dropdownCol.implicitHeight + 12)
            x: Math.max(12, Math.min(root.width - width - 12, root.dropdownAnchorX - width))
            y: (root.dropdownAnchorY + height <= root.height - 12)
                ? root.dropdownAnchorY
                : Math.max(12, root.dropdownAnchorBottomY - height)
            radius: Deck.radiusMedium
            color: Deck.elevated
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.45)

            MouseArea {
                anchors.fill: parent
                onClicked: function(mouse) { mouse.accepted = true; }
            }

            Flickable {
                anchors.fill: parent
                anchors.margins: 6
                contentHeight: dropdownCol.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: dropdownCol
                    width: parent.width
                    spacing: 2

                    Repeater {
                        model: root.dropdownCandidates
                        delegate: Rectangle {
                            id: ddItem
                            required property var modelData
                            readonly property bool isCurrent: root.dropdownAssoc
                                && modelData.desktop_id === root.dropdownAssoc.default_desktop_id
                            width: dropdownCol.width
                            height: 34
                            radius: Deck.radiusSmall
                            color: ddMa.containsMouse
                                ? Deck.alpha(Deck.accent, 0.18)
                                : (isCurrent ? Deck.alpha(Deck.accent, 0.1) : "transparent")

                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 14
                                    text: ddItem.isCurrent ? "✓" : ""
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    font.weight: Font.Bold
                                    color: Deck.accent
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 16
                                    text: root.appIcon(ddItem.modelData.desktop_id, ddItem.modelData.name, root.dropdownAssoc ? root.dropdownAssoc.category : "Other")
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    color: ddItem.isCurrent ? Deck.accent : Deck.fg
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 46
                                    text: ddItem.modelData.name || ddItem.modelData.desktop_id
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    font.weight: ddItem.isCurrent ? Font.DemiBold : Font.Normal
                                    color: ddItem.isCurrent ? Deck.accent : Deck.fg
                                    elide: Text.ElideRight
                                }
                            }

                            MouseArea {
                                id: ddMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.dropdownAssoc) {
                                        DefaultAppsService.setDefaultApp(root.dropdownAssoc.mime_type, ddItem.modelData.desktop_id);
                                        root.closeDropdown();
                                    }
                                }
                            }
                        }
                    }

                    // Divider before "Other Applications..."
                    Rectangle {
                        visible: root.dropdownCandidates.length > 0
                        width: dropdownCol.width - 12
                        height: 1
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Deck.alpha(Deck.muted, 0.2)
                    }

                    // "Other Applications..." entry (opens searchable full-app modal)
                    Rectangle {
                        width: dropdownCol.width
                        height: 34
                        radius: Deck.radiusSmall
                        color: otherAppMa.containsMouse ? Deck.alpha(Deck.accent, 0.18) : "transparent"

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 8

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 14
                                text: "󰀻"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                color: Deck.muted
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 22
                                text: "Other Applications..."
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSize
                                color: Deck.fg
                                elide: Text.ElideRight
                            }
                        }

                        MouseArea {
                            id: otherAppMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.dropdownAssoc) {
                                    root.openPicker(root.dropdownAssoc);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // "Other Applications..." Searchable Modal
    Rectangle {
        id: pickerOverlay
        anchors.fill: parent
        visible: root.pickerAssoc !== null
        color: Deck.alpha(Deck.bg, 0.72)
        z: 95

        MouseArea {
            anchors.fill: parent
            onClicked: root.closePicker()
        }

        Rectangle {
            id: pickerCard
            anchors.centerIn: parent
            width: Math.min(540, Math.max(300, parent.width - 48))
            height: Math.min(560, Math.max(280, parent.height - 48))
            radius: Deck.radiusMedium
            color: Deck.surface
            border.width: 1
            border.color: Deck.alpha(Deck.accent, 0.4)

            MouseArea {
                anchors.fill: parent
                onClicked: function(mouse) { mouse.accepted = true; }
            }

            Column {
                id: pickerHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: Deck.space16
                spacing: Deck.space12

                Item {
                    width: parent.width
                    height: Math.max(pickerTitleCol.implicitHeight, pickerCloseBtn.height)

                    Column {
                        id: pickerTitleCol
                        anchors.left: parent.left
                        anchors.right: pickerCloseBtn.left
                        anchors.rightMargin: Deck.space12
                        spacing: 2

                        Text {
                            width: parent.width
                            text: root.pickerAssoc
                                ? ("Choose Default for " + (root.pickerAssoc.label || root.pickerAssoc.mime_type))
                                : "Choose Default Application"
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeLarge
                            font.weight: Font.Bold
                            color: Deck.fg
                            elide: Text.ElideRight
                        }

                        Text {
                            width: parent.width
                            text: root.pickerAssoc ? root.pickerAssoc.mime_type : ""
                            font.family: Deck.fontFamily
                            font.pixelSize: Deck.fontSizeSmall
                            color: Deck.muted
                            elide: Text.ElideRight
                        }
                    }

                    ActionButton {
                        id: pickerCloseBtn
                        anchors.right: parent.right
                        anchors.top: parent.top
                        compact: true
                        text: "Close"
                        onClicked: root.closePicker()
                    }
                }

                SearchField {
                    id: pickerSearchField
                    width: parent.width
                    height: 34
                    placeholder: "Filter applications..."
                    text: root.pickerSearch
                    onTextChanged: root.pickerSearch = text
                }
            }

            Flickable {
                anchors.top: pickerHeader.bottom
                anchors.topMargin: Deck.space12
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: Deck.space16
                anchors.rightMargin: Deck.space16
                anchors.bottomMargin: Deck.space16
                contentHeight: pickerListCol.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: pickerListCol
                    width: parent.width
                    spacing: Deck.space8

                    Text {
                        visible: root.pickerCompatibleApps.length > 0
                        text: "Recommended Applications"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: Deck.accent
                    }

                    Repeater {
                        model: root.pickerCompatibleApps
                        delegate: Rectangle {
                            id: compatRow
                            required property var modelData
                            readonly property bool isCurrent: root.pickerAssoc
                                && modelData.desktop_id === root.pickerAssoc.default_desktop_id
                            width: pickerListCol.width
                            height: compatRowCol.implicitHeight + 16
                            radius: Deck.radiusSmall
                            color: isCurrent
                                ? Deck.alpha(Deck.accent, 0.18)
                                : (compatMa.containsMouse ? Deck.elevated : Deck.alpha(Deck.bg, 0.5))
                            border.width: 1
                            border.color: isCurrent ? Deck.accent : Deck.alpha(Deck.muted, 0.18)

                            Column {
                                id: compatRowCol
                                anchors.left: parent.left
                                anchors.right: compatTag.left
                                anchors.rightMargin: Deck.space8
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: Deck.space12
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: compatRow.modelData.name || compatRow.modelData.desktop_id
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    font.weight: Font.DemiBold
                                    color: Deck.fg
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: compatRow.modelData.desktop_id
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    color: Deck.muted
                                    elide: Text.ElideRight
                                }
                            }

                            Text {
                                id: compatTag
                                anchors.right: parent.right
                                anchors.rightMargin: Deck.space12
                                anchors.verticalCenter: parent.verticalCenter
                                text: compatRow.isCurrent ? "Current" : "Set Default"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                font.weight: Font.DemiBold
                                color: compatRow.isCurrent ? Deck.accent : Deck.muted
                            }

                            MouseArea {
                                id: compatMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.pickerAssoc) {
                                        DefaultAppsService.setDefaultApp(root.pickerAssoc.mime_type, compatRow.modelData.desktop_id);
                                        root.closePicker();
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        visible: root.pickerOtherApps.length > 0
                        text: "All Installed Applications"
                        font.family: Deck.fontFamily
                        font.pixelSize: Deck.fontSizeSmall
                        font.weight: Font.DemiBold
                        color: Deck.muted
                        topPadding: root.pickerCompatibleApps.length > 0 ? Deck.space8 : 0
                    }

                    Repeater {
                        model: root.pickerOtherApps
                        delegate: Rectangle {
                            id: otherRow
                            required property var modelData
                            readonly property bool isCurrent: root.pickerAssoc
                                && modelData.desktop_id === root.pickerAssoc.default_desktop_id
                            width: pickerListCol.width
                            height: otherRowCol.implicitHeight + 16
                            radius: Deck.radiusSmall
                            color: isCurrent
                                ? Deck.alpha(Deck.accent, 0.18)
                                : (otherMa.containsMouse ? Deck.elevated : Deck.alpha(Deck.bg, 0.45))
                            border.width: 1
                            border.color: isCurrent ? Deck.accent : Deck.alpha(Deck.muted, 0.15)

                            Column {
                                id: otherRowCol
                                anchors.left: parent.left
                                anchors.right: otherTag.left
                                anchors.rightMargin: Deck.space8
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: Deck.space12
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: otherRow.modelData.name || otherRow.modelData.desktop_id
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSize
                                    font.weight: Font.DemiBold
                                    color: Deck.fg
                                    elide: Text.ElideRight
                                }

                                Text {
                                    width: parent.width
                                    text: otherRow.modelData.desktop_id
                                    font.family: Deck.fontFamily
                                    font.pixelSize: Deck.fontSizeSmall
                                    color: Deck.muted
                                    elide: Text.ElideRight
                                }
                            }

                            Text {
                                id: otherTag
                                anchors.right: parent.right
                                anchors.rightMargin: Deck.space12
                                anchors.verticalCenter: parent.verticalCenter
                                text: otherRow.isCurrent ? "Current" : "Set Default"
                                font.family: Deck.fontFamily
                                font.pixelSize: Deck.fontSizeSmall
                                color: otherRow.isCurrent ? Deck.accent : Deck.muted
                            }

                            MouseArea {
                                id: otherMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (root.pickerAssoc) {
                                        DefaultAppsService.setDefaultApp(root.pickerAssoc.mime_type, otherRow.modelData.desktop_id);
                                        root.closePicker();
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
