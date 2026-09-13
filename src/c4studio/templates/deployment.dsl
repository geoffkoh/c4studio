// Containers mapped onto the infrastructure that runs them.
// A deployment view answers "where does this actually run?", which the
// static views deliberately do not.
workspace "My Workspace" "Containers and where they run." {

    model {
        customer = person "Customer" "Uses the product."

        system = softwareSystem "My System" "The system being described." {
            web = container "Web Application" "Serves the UI." "TypeScript, React"
            api = container "API Application" "Business logic and endpoints." "Python, FastAPI"
            database = container "Database" "Stores orders." "PostgreSQL" "Database"
        }

        customer -> web "Places orders using" "HTTPS"
        web -> api "Calls" "JSON/HTTPS"
        api -> database "Reads from and writes to" "SQL"

        production = deploymentEnvironment "Production" {
            deploymentNode "eu-west-1" "The AWS region." "AWS" {
                deploymentNode "Kubernetes Cluster" "Runs the services." "EKS" {
                    deploymentNode "web" "Web pods." "Kubernetes Pod" "" 2 {
                        containerInstance web
                    }
                    deploymentNode "api" "API pods." "Kubernetes Pod" "" 3 {
                        containerInstance api
                    }
                }
                deploymentNode "Managed Database" "Managed instance." "RDS for PostgreSQL" {
                    containerInstance database
                }
            }
        }
    }

    views {
        container system "Containers" "The moving parts inside the system." {
            include *
            autolayout lr
        }

        deployment system "Production" "ProductionDeployment" "Where it runs." {
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
        }
    }
}
