workspace "Delta Release" "Marking what is new, existing and being retired on a diagram." {

    /*
     * Structurizr has no "new" or "existing" keyword. The only styling axis
     * is the *tag*: you tag elements, and style the tag. This sample shows
     * the whole mechanism, including how it reaches the legend.
     *
     * The legend is derived, not declared. c4studio emits one row per
     * visually distinct combination of colour, shape and border, labelled
     * by the most specific style tag that matched — so tagging is all it
     * takes to get a legend row named "New".
     *
     * Note that the unchanged containers are tagged "Existing" rather than
     * left bare. An untagged element falls back to its C4 kind, which would
     * give a legend reading "New" vs "Container" instead of "New" vs
     * "Existing". The actor is deliberately left untagged: it is not part of
     * the delta, so "Person" is the row you want.
     *
     * Declaration order matters for the *label*. Every matching rule applies
     * its own properties, but the last one to match names the legend row —
     * which is why the lifecycle rules come first here and "Datastore",
     * which is meant to name its row, comes after them.
     */

    model {
        analyst = person "Risk Analyst" "Reviews flagged orders."

        platform = softwareSystem "Trading Platform" {

            orders = container "Orders API" "Accepts and validates orders." "Java 21" {
                tags "Existing"
            }

            ledger = container "Ledger" "System of record for fills." "PostgreSQL" {
                tags "Existing, Datastore"
            }

            // This quarter's work.
            fraud = container "Fraud Check" "Scores orders before they reach the ledger." "Go" {
                tags "New"
            }

            review = container "Review Console" "Where analysts triage flagged orders." "React" {
                tags "New"
            }

            // Still running, scheduled for removal once Fraud Check is proven.
            batch = container "Batch Poster" "Nightly settlement job." "COBOL" {
                tags "Deprecated"
            }
        }

        clearing = softwareSystem "Clearing House" "External settlement network." {
            tags "External"
        }

        analyst -> review "Triages flagged orders in"
        orders -> fraud "Screens orders with"
        fraud -> ledger "Writes cleared orders to"
        orders -> batch "Queues settlement through"
        batch -> clearing "Settles via"
        fraud -> clearing "Settles via"
    }

    views {
        systemContext platform "Context" "Who the platform talks to." {
            include *
            autoLayout lr
        }

        container platform "Delta" "What changed this quarter." {
            include *
            autoLayout lr
        }

        styles {
            /*
             * Use `background` and `shape` for the distinction you most want
             * read at a glance: they are the two axes the legend swatch
             * carries, and they survive being printed in greyscale least
             * well but read fastest in colour.
             *
             * `border` and `opacity` are honoured too (PP-107) and are the
             * conventional way to say "planned" and "going away".
             *
             * Avoid `width`, `height`, `fontSize` and `iconPosition` — they
             * parse and export, but no renderer draws them, and `c4 check`
             * will tell you so (PP-108).
             */

            element "Existing" {
                background #4b7bb5
                color #ffffff
            }

            // Dashed and darker: new, and not yet load-bearing.
            element "New" {
                background #2e7d32
                color #ffffff
                border dashed
                strokeWidth 3
            }

            // Faded and dotted: still running, on its way out. The dotted
            // outline is what separates it from "External" in the legend —
            // the swatch carries colour, shape and border, but not opacity,
            // so a fade alone would leave two near-identical grey squares.
            element "Deprecated" {
                background #90a4ae
                color #ffffff
                border dotted
                opacity 55
            }

            // Tags compose: the ledger carries "Existing, Datastore" and
            // gets the blue from one and the cylinder from the other. Only
            // this rule sets a shape, so the shape would survive either way
            // — it is declared last so that it also *names* the row.
            element "Datastore" {
                shape Cylinder
            }

            element "External" {
                background #b0bec5
                color #ffffff
            }
        }
    }
}
