// The two places c4studio shows up that are not its own web app.
//
// Added with `!element` rather than declared inside c4studio.dsl: they are
// containers of the same system, but they are built, versioned and shipped
// separately, so they get their own file.

!element c4studio {

    vscode = container "VS Code Extension" "DSL highlighting, inline diagnostics, and the web app embedded as a side-panel preview. Spawns whatever c4studio is on the machine, so it feature-detects rather than assuming." "TypeScript, esbuild, .vsix" {
        previewMgr  = component "Preview Manager" "Owns the panel and the server behind it. Asks for Viewer mode and falls back when the flag is unknown — VS Code already has the file open, and a second editor writing to it is the one thing the preview must not do." "TypeScript"
        resolver    = component "Server Resolver" "Finds a runnable c4studio: a configured command, the project's own environment, or a managed install." "TypeScript"
        diagnostics = component "Diagnostics Bridge" "Runs `c4 check --json` on save and publishes the results into the Problems panel." "TypeScript"
        grammar     = component "TextMate Grammar" "DSL syntax highlighting. The third copy of the keyword vocabulary, and the one that cannot share the others." "tmLanguage JSON"
    }

    action = container "GitHub Action" "Renders every view as SVG on push, and optionally commits them or comments on the pull request." "composite action, YAML"
}
