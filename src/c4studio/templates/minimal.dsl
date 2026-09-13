// The smallest thing that renders: one person, one system, one view.
// Everything else in c4studio is an elaboration of this shape.
workspace "My Workspace" "A starting point." {

    model {
        user = person "User" "Someone who uses the system."
        system = softwareSystem "My System" "What you are building."

        user -> system "Uses"
    }

    views {
        systemContext system "SystemContext" "The system in its context." {
            include *
            autolayout lr
        }
    }
}
