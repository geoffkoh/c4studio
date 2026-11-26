workspace "Line Styles" "Relationship colours, dashes, thickness, routing, parallel lines and long labels, for checking that c4 render draws what the Studio draws (PP-255)" {

    model {
        trader = person "Trader" "Places and amends orders during the trading day"
        ops = person "Operations" "Watches settlement and fixes breaks"

        exchange = softwareSystem "Exchange Gateway" "Order routing to the exchanges" {
            oms = container "Order Manager" "Keeps the book of working orders" "Java"
            router = container "Smart Router" "Chooses a venue for each child order" "Java"
            fix = container "FIX Engine" "Speaks FIX to each venue" "C++"
            risk = container "Pre-trade Risk" "Blocks orders that breach a limit" "Rust"
            store = container "Order Store" "Every order and every fill" "PostgreSQL" "Database"
            audit = container "Audit Log" "Append-only record for the regulator" "Kafka" "Database"
        }

        venue = softwareSystem "Trading Venue" "A lit exchange" "External"
        settlement = softwareSystem "Settlement" "Clears and settles the day's trades" "External"

        trader -> oms "Places orders with" "HTTPS" "Sync"
        trader -> oms "Is told of fills by" "WebSocket" "Async"
        ops -> store "Investigates breaks in" "SQL" "Manual"

        oms -> risk "Checks every order with, before anything leaves the building, and waits for an answer" "gRPC" "Sync,Critical"
        risk -> oms "Rejects breaching orders back to" "gRPC" "Async"
        oms -> router "Sends parent orders to" "gRPC" "Sync"
        router -> fix "Sends child orders to" "Aeron" "Sync,Critical"
        fix -> venue "Sends orders to" "FIX 4.4" "Sync,Critical"
        venue -> fix "Reports fills to" "FIX 4.4" "Async"
        fix -> oms "Passes fills to" "Aeron" "Async"
        oms -> store "Writes orders and fills to" "JDBC" "Sync"
        oms -> audit "Publishes every state change to" "Kafka" "Async,Faint"
        risk -> audit "Publishes every decision to" "Kafka" "Async,Faint"
        store -> settlement "Sends the day's trades to" "SFTP, end of day" "Batch"
    }

    views {
        container exchange "Containers" "Every relationship style, with lines both ways between the same pair" {
            include *
            autoLayout lr 200 100
        }

        container exchange "ContainersTopDown" "The same view, top to bottom, so the labels land in different places" {
            include *
            autoLayout tb
        }

        dynamic exchange "OrderLifecycle" "One order, from the trader to the venue and back" {
            trader -> oms "Places an order"
            oms -> risk "Checks the limit"
            oms -> router "Sends the parent order"
            router -> fix "Sends a child order"
            fix -> venue "Sends it to the venue"
            venue -> fix "Reports the fill"
            fix -> oms "Passes on the fill"
            oms -> store "Records the fill"
            autoLayout lr
        }

        styles {
            element "Element" {
                color #ffffff
            }
            element "Person" {
                shape Person
                background #08427b
            }
            element "Software System" {
                background #1168bd
            }
            element "Container" {
                background #438dd5
            }
            element "Database" {
                shape Cylinder
            }
            element "External" {
                background #8a8a8a
            }
            relationship "Relationship" {
                color #707070
            }
            relationship "Sync" {
                style solid
                thickness 2
                color #1f4e79
            }
            relationship "Async" {
                style dashed
                color #2e86c1
            }
            relationship "Critical" {
                thickness 4
                color #c0392b
            }
            relationship "Faint" {
                opacity 40
            }
            relationship "Manual" {
                style dotted
                color #7d3c98
                thickness 3
            }
            relationship "Batch" {
                style dotted
                color #b9770e
                routing Orthogonal
            }
        }
    }
}
