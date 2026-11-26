workspace "Shapes Gallery" "Every element shape, border and text size, for checking that c4 render draws what the Studio draws (PP-255)" {

    model {
        visitor = person "Visitor" "Someone browsing the shop on a phone or a laptop"
        robot = person "Price Bot" "An automated client that polls the catalogue every few minutes" "Robot"

        shop = softwareSystem "Corner Shop" "A small online shop, drawn once in every shape the DSL offers" {
            web = container "Storefront" "Server-rendered pages for browsing and checkout" "Python, Django" "Web Browser"
            mobile = container "Phone App" "Native app for repeat customers" "Kotlin" "Mobile Portrait"
            tablet = container "Till App" "The in-store till, on a tablet held sideways" "Swift" "Mobile Landscape"
            api = container "Shop API" "Prices, stock and orders" "Python, FastAPI" "Hexagon"
            worker = container "Order Worker" "Takes orders off the queue and books the courier" "Python" "Rounded"
            queue = container "Order Queue" "Orders waiting for the worker" "RabbitMQ" "Pipe"
            db = container "Shop Database" "Products, customers, orders" "PostgreSQL" "Database"
            files = container "Product Photos" "Images uploaded by staff" "Amazon S3" "Bucket"
            exports = container "Nightly Exports" "CSV files the accountant collects" "SFTP" "Folder"
            admin = container "Admin Console" "Back-office screens for staff" "React" "Window"
            cli = container "Ops Shell" "Scripts staff run by hand when something is stuck" "Bash" "Terminal"
            search = container "Search Index" "Typo-tolerant product search with a deliberately long description that has to wrap over several lines in both renderers" "Meilisearch" "Ellipse"
            rules = container "Discount Rules" "Decides which offer applies" "Python" "Diamond"
            health = container "Heartbeat" "Pings every part once a minute" "Go" "Circle"
            plugin = container "Payment Plug-in" "Card payments, embedded in checkout" "JavaScript" "Component"
        }

        courier = softwareSystem "Courier Booking" "Books parcel collections" "External"
        legacy = softwareSystem "Old Stock System" "Being retired; still the source of stock counts for the warehouse" "External,Retiring"

        visitor -> web "Browses and buys from" "HTTPS"
        visitor -> mobile "Reorders from" "HTTPS"
        robot -> api "Polls prices from" "JSON/HTTPS"
        tablet -> api "Rings up sales through" "JSON/HTTPS"
        web -> api "Calls" "JSON/HTTPS"
        mobile -> api "Calls" "JSON/HTTPS"
        web -> plugin "Embeds"
        api -> db "Reads and writes" "SQL"
        api -> search "Queries" "HTTP"
        api -> rules "Asks for the price after discounts"
        api -> queue "Publishes orders to" "AMQP"
        worker -> queue "Consumes orders from" "AMQP"
        worker -> courier "Books collections with" "REST"
        worker -> exports "Writes the day's orders to" "CSV"
        admin -> api "Manages the catalogue through" "JSON/HTTPS"
        admin -> files "Uploads photos to" "S3 API"
        cli -> db "Fixes stuck orders in" "psql"
        health -> api "Pings" "HTTP"
        api -> legacy "Reads stock counts from" "SOAP"
    }

    views {
        systemContext shop "Context" "The shop and who it talks to" {
            include *
            autoLayout lr
        }

        container shop "Containers" "Every shape at once" {
            include *
            autoLayout tb 120 80
        }

        styles {
            element "Element" {
                color #ffffff
            }
            element "Person" {
                shape Person
                background #08427b
            }
            element "Robot" {
                shape Robot
                background #5a3d8a
            }
            element "Software System" {
                background #1168bd
            }
            element "Container" {
                background #438dd5
            }
            element "External" {
                background #8a8a8a
                border dashed
            }
            element "Retiring" {
                border dotted
                strokeWidth 4
                stroke #c0392b
                opacity 70
            }
            element "Web Browser" {
                shape WebBrowser
            }
            element "Mobile Portrait" {
                shape MobileDevicePortrait
            }
            element "Mobile Landscape" {
                shape MobileDeviceLandscape
            }
            element "Hexagon" {
                shape Hexagon
                background #2d7d46
            }
            element "Rounded" {
                shape RoundedBox
            }
            element "Pipe" {
                shape Pipe
                background #b9770e
            }
            element "Database" {
                shape Cylinder
                background #1a5276
            }
            element "Bucket" {
                shape Bucket
                background #b9770e
            }
            element "Folder" {
                shape Folder
                background #f4d03f
                color #333333
            }
            element "Window" {
                shape Window
            }
            element "Terminal" {
                shape Terminal
                background #222222
                color #2ecc71
            }
            element "Ellipse" {
                shape Ellipse
            }
            element "Diamond" {
                shape Diamond
                background #7d3c98
            }
            element "Circle" {
                shape Circle
                background #c0392b
            }
            element "Component" {
                shape Component
                background #85bbf0
                color #000000
            }
        }
    }
}
