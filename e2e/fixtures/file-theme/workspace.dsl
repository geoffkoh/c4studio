// A workspace whose only theme is a file beside it (PP-199), so the
// preview's icon test needs no network. The icon is drawn for this test;
// no third-party artwork is redistributed.
workspace "Offline Theme" "Icons from a file-based theme" {

    model {
        user = person "User" "Someone using the system"
        shop = softwareSystem "Shop" "Sells things" {
            web = container "Web App" "Takes orders" "TypeScript"
            db = container "Orders DB" "Stores orders" "PostgreSQL" "Database"
        }
        user -> web "Places orders with"
        web -> db "Reads and writes" "SQL"
    }

    views {
        container shop Containers "Shop – Containers" {
            include *
            autoLayout lr
        }

        theme "theme/theme.json"
    }
}
