workspace "Icons and Groups" "Full-colour and tinted icons, a workspace logo, nested groups and a perspective, for checking that c4 render draws what the Studio draws (PP-255)" {

    model {
        analyst = person "Analyst" "Builds reports from the warehouse"

        group "Data Platform" {
            lake = softwareSystem "Data Lake" "Raw and curated data for the whole company" {
                group "Ingestion" {
                    collector = container "Event Collector" "Accepts events from every product" "Go" "Function" {
                        perspectives {
                            owner "Platform team"
                            cost "High"
                        }
                    }
                    stream = container "Event Stream" "Buffers events for an hour" "Kafka" "Queue" {
                        perspectives {
                            owner "Platform team"
                        }
                    }
                }
                group "Storage" {
                    raw = container "Raw Zone" "Events exactly as they arrived" "Amazon S3" "Bucket" {
                        perspectives {
                            owner "Platform team"
                            cost "Medium"
                        }
                    }
                    warehouse = container "Warehouse" "Modelled tables for reporting" "Snowflake" "Database" {
                        perspectives {
                            owner "Analytics team"
                            cost "High"
                        }
                    }
                }
                group "Serving" {
                    transform = container "Transform Jobs" "Turns raw events into modelled tables" "dbt" "Tinted"
                    bi = container "Report Server" "Dashboards for the business" "Superset" "Server" {
                        perspectives {
                            owner "Analytics team"
                            cost "Low"
                        }
                    }
                    edge = container "Edge Cache" "Caches dashboard queries near the reader" "Cloudflare" "Auto Tint"
                }
            }
        }

        products = softwareSystem "Product Apps" "Web and phone apps that emit events" "External,Mobile"

        products -> collector "Sends events to" "HTTPS"
        collector -> stream "Publishes to" "Kafka"
        stream -> raw "Is archived to" "S3 sink"
        transform -> raw "Reads from" "S3 API"
        transform -> warehouse "Writes models to" "SQL"
        bi -> warehouse "Queries" "SQL"
        edge -> bi "Caches" "HTTPS"
        analyst -> edge "Views dashboards through" "HTTPS"
    }

    views {
        systemLandscape "Landscape" "The platform among the company's systems" {
            include *
            autoLayout lr
        }

        container lake "Containers" "Every icon kind, inside nested groups" {
            include *
            autoLayout lr
        }

        styles {
            element "Workspace:Icon" {
                icon "brand/northwind-logo.svg"
            }
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
            element "External" {
                background #8a8a8a
            }
            element "Mobile" {
                icon "icons/basic/Mobile_48.svg"
            }
            element "Function" {
                icon "icons/basic/Function_48.svg"
            }
            element "Queue" {
                icon "icons/basic/Queue_48.svg"
            }
            element "Bucket" {
                shape Bucket
                icon "icons/basic/Bucket_48.svg"
                background #b9770e
            }
            element "Database" {
                shape Cylinder
                icon "icons/basic/Database_48.svg"
            }
            element "Server" {
                icon "icons/basic/Server_48.svg"
            }
            element "Tinted" {
                icon "icons/outline/Queue.svg"
                background #f4d03f
                color #333333
                properties {
                    "c4studio.iconTint" "true"
                }
            }
            element "Auto Tint" {
                icon "icons/outline/Cloud.svg"
                background #2d7d46
            }
        }
    }
}
