workspace "c4studio" "c4studio described in its own DSL, rendered by itself." {

    !docs docs
    !adrs adrs

    model {
        # Split across model/ so each file stays readable on its own. Both
        # comment forms work here: `#` only opens a comment at the start of
        # a line, so the `#08427b` in styles below is still a colour.
        !include model/people.dsl
        !include model/c4studio.dsl
        !include model/integrations.dsl
        !include model/externals.dsl
        !include model/relationships.dsl
        !include model/deployment.dsl
    }

    views {
        systemLandscape Landscape "c4studio – System Landscape" {
            include *
            autoLayout
        }

        systemContext c4studio Context "c4studio – System Context" {
            include *
            autoLayout
        }

        container c4studio Containers "c4studio – Containers" {
            include *
            autoLayout
        }

        // Everything that never touches the network, which is most of it.
        filtered Containers exclude "Network" Offline "c4studio – What works offline"

        component core CoreComponents "Core Library – Components" {
            include *
            autoLayout
        }

        component backend BackendComponents "Web Backend – Components" {
            include *
            autoLayout
        }

        component spa SpaComponents "Studio SPA – Components" {
            include *
            autoLayout
        }

        component diagramCore DiagramCoreComponents "Diagram Core – Components" {
            include *
            autoLayout lr
        }

        component vscode VscodeComponents "VS Code Extension – Components" {
            include *
            autoLayout lr
        }

        dynamic c4studio SaveLoop "Dynamic – typing a change and seeing it" {
            developer -> dslEditor "Types in the editor"
            dslEditor -> apiClient "Debounced check of the unsaved buffer"
            apiClient -> routes "POST /api/check"
            routes -> loader "Parses the buffer in its root's context"
            developer -> dslEditor "Presses Cmd+S"
            apiClient -> routes "PUT /api/source"
            routes -> writer "Writes atomically, fingerprint checked"
            writer -> sources "Replaces the file"
            routes -> loader "Reloads synchronously and returns the generation"
            appShell -> apiClient "Refetches the view"
            apiClient -> routes "GET /api/views/{key}/graph"
            routes -> flowGraph "Rebuilds the payload"
            flowGraph -> viewGraph "From the reparsed workspace"
            appShell -> graphPane "Redraws"
            autoLayout lr
        }

        dynamic c4studio HeadlessRender "Dynamic – the same diagram, with no browser" {
            ci -> action "Runs the action on push"
            action -> cli "c4 render workspace.dsl -o diagrams/"
            cli -> dslParser "Parses the source"
            cli -> viewGraph "Builds the same graph the web app serves"
            cli -> renderer "Pipes the payload to the bundled Node renderer"
            renderer -> svgRender "Draws it as SVG markup"
            autoLayout lr
        }

        deployment c4studio "Developer machine" LocalDeployment "Developer machine – one process, one browser" {
            include *
            autoLayout
        }

        deployment c4studio "CI" CiDeployment "CI – the same code, headless" {
            include *
            autoLayout
        }

        styles {
            element "Person" {
                background #08427b
                color #ffffff
                shape Person
            }
            element "External System" {
                background #8a94a6
                color #ffffff
            }
            element "File Store" {
                shape Folder
            }
            element "Network" {
                background #b4584e
                color #ffffff
            }
        }
    }
}
