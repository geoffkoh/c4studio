// Two environments, and the contrast between them is the architecture.
//
// "Developer machine" is the whole product: one process, one browser, no
// server, no accounts. "CI" is the same code with no browser at all —
// which is possible only because layout and painting live in a library
// rather than in the app.

deploymentEnvironment "Developer machine" {

    laptop = deploymentNode "Laptop" "Whatever the user runs: macOS, Linux or Windows." "OS" {

        python = deploymentNode "Python 3.13 environment" "pipx, uv or a virtualenv." "CPython" {
            containerInstance cli
            containerInstance core
            backendInstance = containerInstance backend
        }

        node = deploymentNode "Node 18+" "Only needed by `c4 render`; the web app and everything else work without it." "Node.js" {
            containerInstance renderer
        }

        browser = deploymentNode "Browser" "Points at 127.0.0.1. No authentication, because there is nothing to authenticate to." "Chrome, Firefox or Safari" {
            containerInstance spa
            containerInstance diagramCore
        }

        editor = deploymentNode "VS Code" "Optional." "Electron" {
            containerInstance vscode
        }

        disk = deploymentNode "Working copy" "A git repository, usually." "Filesystem" {
            containerInstance sources
            containerInstance layoutSidecars
        }
    }
}

deploymentEnvironment "CI" {

    runner = deploymentNode "GitHub Actions runner" "Ephemeral, headless." "ubuntu-latest" {

        actionStep = deploymentNode "c4studio action step" "" "composite action" {
            containerInstance action
        }

        ciPython = deploymentNode "Python 3.13" "" "CPython" {
            containerInstance cli
            containerInstance core
        }

        ciNode = deploymentNode "Node 18+" "Bundled in the wheel, so there is no npm install." "Node.js" {
            containerInstance renderer
        }

        checkout = deploymentNode "Checkout" "" "Filesystem" {
            containerInstance sources
        }
    }
}
