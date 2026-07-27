/*
 * Grammar fixture for the Structurizr DSL extension.
 *
 * Exercises every term the syntax highlighter scopes, so the grammar can be
 * checked by eye after a change: open this file with the extension active
 * and confirm block/element/view keywords, attribute names, style
 * properties, directives, strings, colours, numbers and booleans all
 * colour. It is real DSL and parses — a parser test keeps it that way, so
 * it cannot drift into something the language does not accept.
 */
workspace "Highlighting" "Every highlighted term in one file" {

    !const ORG "Example Ltd"

    model {
        customer = person "Customer" "Buys things" "External" {
            url https://example.com/customer
            tags "Person" "External"
            perspectives {
                "Security" "Handles personal data"
            }
        }

        group "Internal" {
            shop = softwareSystem "Shop" "Sells things" {
                description "Overridden description"
                properties {
                    "owner" "platform-team"
                }
                web = container "Web" "Storefront" "TypeScript" {
                    technology "React"
                    api = component "API Client" "Calls the backend" "fetch"
                }
                db = container "Database" "Stores orders" "Postgres"
            }
        }

        payments = softwareSystem "Payments" "Takes money" "External System"

        customer -> web "Buys from" "HTTPS" {
            tags "Sync"
            url https://example.com/checkout
        }
        web -> db "Reads and writes" "SQL"
        shop -> payments "Charges via" "REST"

        deploymentEnvironment "Production" {
            deploymentGroup "shop"
            aws = deploymentNode "AWS" "Cloud" "eu-west-1" {
                instances 3
                dns = infrastructureNode "Route 53" "DNS" {
                    healthCheck "liveness" "https://example.com/health" 60 200
                }
                node = deploymentNode "ECS" "Container host" "Fargate" {
                    containerInstance web
                }
                shopInstance = softwareSystemInstance shop
            }
        }
    }

    views {
        systemLandscape Landscape "Everything" {
            include *
            autoLayout lr 300 300
        }

        systemContext shop Context "Shop in context" {
            include *
            exclude payments
            autoLayout
        }

        container shop Containers {
            include *
            autoLayout tb
        }

        component web Components {
            include *
            autoLayout
        }

        dynamic shop Checkout "A purchase" {
            customer -> web "Places an order"
            web -> db "Records it"
            autoLayout
        }

        deployment shop "Production" Live {
            include *
            autoLayout
        }

        filtered Landscape exclude "External" Internal "Internal only"

        custom Notes "Free-form" {
            title "Custom view"
        }

        image web Screenshot {
            kroki plantuml https://example.com/diagram.puml
            title "An image view"
        }

        styles {
            element "Person" {
                shape Person
                background #1168bd
                colour #ffffff
                stroke #0b4884
                strokeWidth 2
                fontSize 22
                border solid
                opacity 90
                metadata true
                description false
                icon https://example.com/icon.png
                iconPosition Top
                width 450
                height 300
            }
            relationship "Sync" {
                thickness 2
                color #707070
                dashed false
                routing Direct
                position 50
                style solid
                font "Arial"
                opacity 80
            }
        }

        theme default
        themes https://static.structurizr.com/themes/default/theme.json

        branding {
            logo https://example.com/logo.png
            font "Open Sans" https://example.com/font.css
        }

        terminology {
            person "Actor"
            softwareSystem "System"
        }

        configuration {
            scope softwaresystem
            visibility private
            users {
                "alice@example.com" read
            }
        }
    }
}
