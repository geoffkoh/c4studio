// Everything outside the machine c4studio runs on.
//
// There are fewer of these than a tool this size usually has, and that is
// the point: only two are reached at run time, and only one of those sends
// anything out.

anthropic = softwareSystem "Anthropic API" "Answers the assistant's requests for a rewritten DSL file." "External System" {
    tags "Network"
}

themeCdn = softwareSystem "Structurizr Theme CDN" "Serves theme JSON and the service icons a themed diagram embeds." "External System" {
    tags "Network"
}

pypi = softwareSystem "PyPI" "Distributes the c4studio wheel, bundle and renderer included." "External System"

git = softwareSystem "Git Repository" "Where the DSL lives, and how diagrams are shared. c4studio has no sharing of its own." "External System"

ci = softwareSystem "CI (GitHub Actions)" "Runs the c4studio action on every push to render views without a browser." "External System"
