// The two places c4studio shows up that are not its own web app.
//
// Added with `!element` rather than declared inside c4studio.dsl: they are
// containers of the same system, but they are built, versioned and shipped
// separately, so they get their own file.

!element c4studio {

    vscode = container "VS Code Extension" "DSL highlighting, inline diagnostics, and a preview that draws one view as an SVG beside the editor. Runs whatever c4studio is on the machine, so it feature-detects rather than assuming." "TypeScript, esbuild, .vsix" {
        previewMgr  = component "Preview Manager" "Owns the preview panel: renders the chosen view with `c4 render --view` and shows the SVG, with no server and no port. Starts the Studio in a browser only when asked." "TypeScript"
        resolver    = component "Server Resolver" "Finds a runnable c4studio: a configured command, the project's own environment, or a managed install." "TypeScript"
        diagnostics = component "Diagnostics Bridge" "Runs `c4 check --json` on save and publishes the results into the Problems panel." "TypeScript"
        grammar     = component "TextMate Grammar" "DSL syntax highlighting. The third copy of the keyword vocabulary, and the one that cannot share the others." "tmLanguage JSON"
    }

    action = container "GitHub Action" "Renders every view as SVG on push, and optionally commits them or comments on the pull request." "composite action, YAML"
}
