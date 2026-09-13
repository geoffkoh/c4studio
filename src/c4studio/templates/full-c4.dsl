// All three static C4 levels in one file: context, containers, components.
// Drill from one to the next in the viewer by double-clicking an element.
workspace "My Workspace" "Context, containers and components." {

    model {
        customer = person "Customer" "Uses the product."

        system = softwareSystem "My System" "The system being described." {
            web = container "Web Application" "Serves the UI." "TypeScript, React"
            api = container "API Application" "Business logic and endpoints." "Python, FastAPI" {
                controller = component "Order Controller" "Handles order requests." "FastAPI router"
                service = component "Order Service" "Applies the order rules." "Python"
                repository = component "Order Repository" "Reads and writes orders." "SQLAlchemy"
            }
            database = container "Database" "Stores orders and customers." "PostgreSQL" "Database"
        }

        payments = softwareSystem "Payment Provider" "Takes payments." "External"

        customer -> web "Places orders using" "HTTPS"
        web -> api "Calls" "JSON/HTTPS"
        api -> database "Reads from and writes to" "SQL"
        api -> payments "Charges cards via" "HTTPS"

        controller -> service "Delegates to"
        service -> repository "Loads and stores orders with"
        repository -> database "Queries" "SQL"
    }

    views {
        systemContext system "SystemContext" "The system in its context." {
            include *
            autolayout lr
        }

        container system "Containers" "The moving parts inside the system." {
            include *
            autolayout lr
        }

        component api "ApiComponents" "Inside the API application." {
            include *
            autolayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Database" {
                shape Cylinder
            }
            element "External" {
                background #999999
                color #ffffff
            }
        }
    }
}
