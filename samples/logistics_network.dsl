// NorthWind Logistics — a parcel-delivery network, and the sample that
// exercises the widest slice of the DSL. Where the other samples stay
// close to the everyday keywords, this one deliberately reaches for the
// rest of the supported language: groups, custom elements, `this ->`,
// relationship bodies, bulk `!element`/`!elements`/`!relationships`,
// deployment groups, software-system instances, health checks, view
// animation/properties, branding and terminology. `docs/dsl-support.md`
// is the keyword-by-keyword map; tests/test_samples pins that everything
// used here actually lands in the model.
workspace "NorthWind Logistics" "Parcel network: booking, routing, tracking and delivery" {

    // Identifier resolution is always flat in c4studio; saying so here
    // simply makes the behaviour explicit.
    !identifiers flat

    // With implied relationships on, `shipper -> portal` below also
    // yields shipper -> Delivery Platform for the context views.
    !impliedRelationships true

    configuration {
        scope landscape
        visibility private
        users {
            geoff write
        }
    }

    model {
        group "Customers & Partners" {
            shipper  = person "Shipper" "Books parcel pickups, prints labels and pays for postage"
            receiver = person "Receiver" "Tracks inbound parcels and reschedules delivery windows"
        }

        group "Operations" {
            courier    = person "Courier" "Collects and delivers parcels along an optimised route"
            dispatcher = person "Dispatcher" "Watches the live network and intervenes on exceptions"
        }

        platform = softwareSystem "Delivery Platform" "Booking, routing, tracking and notifications for the parcel network" {
            group "Customer Channels" {
                portal = container "Booking Portal" "Web UI for booking pickups, printing labels and tracking parcels" "TypeScript, React"
                courierApp = container "Courier App" "Offline-first mobile app: manifests, scan events, proof of delivery" "Kotlin, Android" {
                    tags "Mobile App"
                }
            }

            group "Core Services" {
                bookingApi = container "Booking API" "Creates shipments, quotes prices, allocates tracking numbers" "Python, FastAPI" {
                    url "https://api.northwind.example/booking"
                    properties {
                        owner "booking-team"
                        tier "1"
                    }
                    perspectives {
                        security "OAuth2 client credentials; PII encrypted at rest"
                        capacity "Sized for 400 bookings/s at peak season"
                    }
                    this -> shipmentDb "Reads and writes shipments" "SQL/TCP"
                }

                routing = container "Routing Engine" "Plans depot-to-door routes and re-plans on disruption" "Python" {
                    // A per-boundary layout hint: wherever this container
                    // renders as a boundary (its component view, or when
                    // expanded in place), its children flow left to right
                    // regardless of the view's own autoLayout direction.
                    properties {
                        "c4studio.autolayout" "lr"
                    }
                    optimizer = component "Route Optimizer" "Solves the vehicle-routing problem per depot" "OR-Tools"
                    trafficAdapter = component "Traffic Adapter" "Normalises live traffic and road-closure feeds" "Python"
                    manifestBuilder = component "Manifest Builder" "Turns optimised routes into courier manifests" "Python"

                    trafficAdapter -> optimizer "Feeds live travel times to"
                    optimizer -> manifestBuilder "Hands optimised stop sequences to"
                }

                tracking = container "Tracking Service" "Maintains the scan history and live position of every parcel" "Go"
                notifier = container "Notification Service" "Sends delivery windows, delay alerts and proof-of-delivery receipts" "Go"
            }

            shipmentDb = container "Shipment Database" "System of record for shipments, labels and scan events" "PostgreSQL" {
                tags "Database"
            }
            eventBus = container "Event Bus" "Scan, booking and route events between services" "Kafka" {
                tags "Message Bus"
            }
        }

        // Deployed on depot hardware below via softwareSystemInstance.
        labelSvc = softwareSystem "Label Service" "Renders carrier-compliant label PDFs at the depot" "Go"

        maps       = softwareSystem "Mapping Provider" "Geocoding, routing graphs and live traffic" "External System"
        payments   = softwareSystem "Payment Gateway" "Card and invoice payments for postage" "External System"
        smsGateway = softwareSystem "SMS Gateway" "Delivery notifications by text message" "External System"

        // A custom element: parsed and round-tripped, though the built-in
        // views do not draw it (docs/dsl-support.md, `element`).
        telematics = element "Telematics Unit" "IoT Device" "Vehicle-mounted GPS and scanner hardware" "IoT"

        // People and channels.
        shipper  -> portal "Books pickups and prints labels with"
        receiver -> portal "Tracks parcels with"
        courier  -> courierApp "Scans parcels and captures signatures in"
        dispatcher -> tracking "Watches the live network via"

        // Front-of-house to core.
        portal -> bookingApi "Creates shipments via" "JSON/HTTPS"
        portal -> tracking "Fetches parcel status from" "JSON/HTTPS"
        bookingApi -> payments "Takes postage payment via" "HTTPS"
        bookingApi -> eventBus "Publishes booking events to" "Kafka" "Async"

        // Routing and the road.
        routing -> maps "Pulls routing graphs and traffic from" "HTTPS"
        routing -> eventBus "Publishes route plans to" "Kafka" "Async"
        courierApp -> eventBus "Streams scan events to" "Kafka" "Async"
        telematics -> eventBus "Streams vehicle positions to" "MQTT" "Async"

        // A relationship with a body: tags, url, properties and
        // perspectives all attach to the relationship itself.
        tracking -> eventBus "Consumes scan and position events from" "Kafka" {
            tags "Async"
            url "https://wiki.northwind.example/tracking/consumers"
            properties {
                consumerGroup "tracking-v2"
            }
            perspectives {
                reliability "At-least-once; scan events are idempotent by scan id"
            }
        }

        notifier -> eventBus "Consumes delivery milestones from" "Kafka" "Async"
        notifier -> smsGateway "Sends delivery texts via" "HTTPS"
        bookingApi -> labelSvc "Requests label PDFs from" "gRPC"

        // Bulk operations: extend one element, every element matching an
        // expression, and every relationship matching an expression.
        !element courierApp {
            url "https://play.example.com/store/apps/northwind-courier"
        }
        !elements "element.tag==Database" {
            properties {
                backup "PITR, 35 days"
            }
        }
        !relationships "relationship.tag==Async" {
            properties {
                delivery "at-least-once"
            }
        }

        deploymentEnvironment "Production" {
            deploymentGroup "Primary Region"
            deploymentGroup "Failover Region"

            deploymentNode "AWS eu-west-1" "Primary cloud region" "Amazon Web Services" {
                deploymentNode "EKS Cluster" "Stateless workloads" "Kubernetes 1.31" "" "3" {
                    bookingInst  = containerInstance bookingApi "Primary Region" {
                        healthCheck "Booking API liveness" "https://api.northwind.example/booking/health" 30 2
                    }
                    routingInst  = containerInstance routing "Primary Region"
                    trackingInst = containerInstance tracking "Primary Region,Failover Region"
                    notifierInst = containerInstance notifier "Primary Region"
                }
                deploymentNode "MSK" "Managed Kafka" "3 brokers, 3 AZs" {
                    busInst = containerInstance eventBus "Primary Region"
                }
                deploymentNode "RDS" "Managed PostgreSQL" "db.r6g.xlarge, Multi-AZ" {
                    dbInst = containerInstance shipmentDb "Primary Region"
                }
                alb = infrastructureNode "Application Load Balancer" "Terminates TLS for the public APIs" "AWS ALB"
            }

            // One edge server per depot: the node count is a range, not a
            // number — `instances` accepts "0..N" just like structurizr.
            deploymentNode "Depot Edge Server" "Runs at every parcel depot" "Intel NUC, Ubuntu LTS" "" "0..N" {
                labelInst = softwareSystemInstance labelSvc "Primary Region" {
                    healthCheck "Label renderer" "http://depot.local:7000/health" 60 5
                }
            }

            alb -> bookingInst "Routes public API traffic to" "HTTPS"
        }
    }

    views {
        // Two themes merge left to right; workspace styles still win.
        themes "https://static.structurizr.com/themes/amazon-web-services-2023.01.31/theme.json" "https://static.structurizr.com/themes/kubernetes-v0.3/theme.json"

        systemLandscape NetworkLandscape "NorthWind – System Landscape" {
            include *
            autoLayout
            default
        }

        filtered NetworkLandscape exclude "External System" InternalLandscape "NorthWind – Internal Systems"

        systemContext platform PlatformContext "Delivery Platform – System Context" {
            include *
            autoLayout lr
            title "Delivery Platform in its neighbourhood"
            description "Who books, who delivers, and which vendors the platform leans on"
            properties {
                audience "new joiners"
            }
            animation {
                shipper receiver courier dispatcher
                platform
                maps payments smsGateway
            }
        }

        container platform PlatformContainers "Delivery Platform – Containers" {
            include *
            autoLayout
            // Groups cannot carry properties, so a group boundary's layout
            // hint is keyed by group name on the view instead.
            properties {
                "c4studio.autolayout.Core Services" "lr"
            }
        }

        // The same containers with the Kafka chatter hidden: exclude takes
        // relationship expressions as well as identifiers.
        container platform PlatformSyncOnly "Delivery Platform – Synchronous calls only" {
            include *
            exclude "relationship.tag==Async"
            autoLayout lr 300 150
        }

        component routing RoutingComponents "Routing Engine – Components" {
            include *
            autoLayout lr
        }

        dynamic platform BookParcel "Dynamic – Booking a pickup" {
            shipper -> portal "Books a next-day pickup"
            portal -> bookingApi "Creates the shipment" "JSON/HTTPS"
            bookingApi -> payments "Charges postage"
            bookingApi -> shipmentDb "Persists the shipment"
            bookingApi -> labelSvc "Renders the label"
            bookingApi -> eventBus "Publishes shipment-created"
            routing -> eventBus "Picks the shipment up for tonight's route plan"
            autoLayout lr
        }

        deployment * "Production" ProductionDeployment "Production – Full Estate" {
            include *
            autoLayout
        }

        styles {
            element "Person" {
                shape Person
                background #1b5e20
                // Colour-scheme variants parse; the viewer paints one scheme.
                dark {
                    background #66bb6a
                    color #0b2e0c
                }
            }
            element "External System" {
                background #8a94a6
                color #ffffff
            }
            element "Database" {
                shape Cylinder
            }
            element "Message Bus" {
                shape Pipe
            }
            element "Mobile App" {
                shape MobileDevicePortrait
            }
            // Relationships default to dashed (the Structurizr house
            // style), so async traffic is marked dotted and coloured —
            // "dashed true" would no longer distinguish anything.
            relationship "Async" {
                style dotted
                color #7b1fa2
            }
        }

        branding {
            logo "https://static.northwind.example/brand/logo.png"
            font "Inter" "https://fonts.googleapis.com/css2?family=Inter"
        }

        terminology {
            person "Actor"
            container "Service"
            deploymentNode "Host"
        }
    }
}
