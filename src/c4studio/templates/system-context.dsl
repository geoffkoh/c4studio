// A system in its context: who uses it, and what it depends on.
// This is usually the first diagram worth drawing and often the only one
// a non-technical audience needs.
workspace "My Workspace" "System context for My System." {

    model {
        customer = person "Customer" "Uses the product."
        staff = person "Support Staff" "Handles queries." "Internal"

        system = softwareSystem "My System" "The system being described."

        email = softwareSystem "Email System" "Sends notifications." "External"
        payments = softwareSystem "Payment Provider" "Takes payments." "External"

        customer -> system "Places orders using"
        staff -> system "Answers queries with"
        system -> email "Sends mail via" "SMTP"
        system -> payments "Charges cards via" "HTTPS"
    }

    views {
        systemContext system "SystemContext" "The system and its neighbours." {
            include *
            autolayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
        }
    }
}
