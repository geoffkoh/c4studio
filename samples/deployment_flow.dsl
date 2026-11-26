workspace "Deployment Flow" "Nested deployment nodes, infrastructure, instances and a dynamic view, for checking that c4 render draws what the Studio draws (PP-255)" {

    model {
        rider = person "Rider" "Books a ride from the app"
        driver = person "Driver" "Accepts rides and drives"

        rides = softwareSystem "Ride Hailing" "Matches riders with nearby drivers" {
            app = container "Rider App" "Books rides and shows the car approaching" "React Native" "Mobile"
            driverApp = container "Driver App" "Offers rides and navigates" "React Native" "Mobile"
            gateway = container "API Gateway" "One door for both apps" "Envoy"
            matcher = container "Matcher" "Pairs each request with the closest free driver" "Go"
            location = container "Location Service" "Where every driver is, a few seconds ago" "Go"
            trips = container "Trip Service" "Trips from request to payment" "Kotlin"
            geo = container "Location Store" "Driver positions, expired after a minute" "Redis" "Database"
            tripDb = container "Trip Database" "Every trip" "PostgreSQL" "Database"
        }

        payments = softwareSystem "Card Payments" "Charges the rider at the end of the trip" "External"

        rider -> app "Books rides with"
        driver -> driverApp "Takes rides with"
        app -> gateway "Calls" "HTTPS"
        driverApp -> gateway "Calls and streams its position to" "HTTPS, WebSocket"
        gateway -> trips "Routes trip requests to" "gRPC"
        gateway -> location "Routes positions to" "gRPC"
        trips -> matcher "Asks for a driver" "gRPC"
        matcher -> location "Finds nearby drivers with" "gRPC"
        location -> geo "Reads and writes positions" "RESP"
        trips -> tripDb "Reads and writes trips" "SQL"
        trips -> payments "Charges the rider through" "HTTPS"

        live = deploymentEnvironment "Live" {
            phone = deploymentNode "Customer's Phone" "" "iOS or Android" "" "1000000" {
                containerInstance app
                containerInstance driverApp
            }
            cloud = deploymentNode "Cloud" "" "AWS" {
                region = deploymentNode "eu-west-1" "" "AWS region" {
                    dns = infrastructureNode "DNS" "Routes the apps to the nearest load balancer" "Route 53"
                    lb = infrastructureNode "Load Balancer" "Terminates TLS" "ALB"
                    cluster = deploymentNode "Kubernetes" "" "EKS" {
                        gatewayPod = deploymentNode "gateway" "" "Pod" "" "3" {
                            containerInstance gateway
                        }
                        servicePods = deploymentNode "services" "" "Pod" "" "6" {
                            containerInstance trips
                            containerInstance matcher
                            containerInstance location
                        }
                    }
                    cache = deploymentNode "ElastiCache" "" "Redis 7" {
                        containerInstance geo
                    }
                    rds = deploymentNode "RDS" "" "PostgreSQL 16" "" "2" {
                        containerInstance tripDb
                    }
                }
            }
            dns -> lb "Resolves to"
            lb -> gatewayPod "Forwards to" "HTTPS"
        }
    }

    views {
        container rides "Containers" "The ride-hailing system's containers" {
            include *
            autoLayout lr
        }

        deployment rides live "LiveDeployment" "Live, in one region" {
            include *
            autoLayout lr
        }

        dynamic rides "BookARide" "From the rider's tap to a driver on the way" {
            rider -> app "Taps Book"
            app -> gateway "Requests a trip"
            gateway -> trips "Creates the trip"
            trips -> matcher "Asks for a driver"
            matcher -> location "Finds the closest free drivers"
            location -> geo "Reads positions near the rider"
            trips -> tripDb "Records the match"
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
            element "Mobile" {
                shape MobileDevicePortrait
            }
            element "External" {
                background #8a8a8a
            }
            element "Infrastructure Node" {
                background #ffffff
                color #333333
                stroke #888888
            }
            element "Deployment Node" {
                color #333333
                stroke #888888
            }
        }
    }
}
