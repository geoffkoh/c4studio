# The Studio

The Studio is a local web app for writing Structurizr DSL and seeing the diagrams it produces. It is a FastAPI server and a React app, both shipped inside the Python package, so you need no Node toolchain to run it.

```bash
c4 webapp shop.dsl          # one workspace
c4 webapp architecture/     # browse every .dsl and .json file in a directory
c4 webapp shop.dsl --port 9000 --no-browser
```

![The c4studio Studio with the source editor open beside a container diagram](assets/editor.jpg)

## Studio and Viewer

| Mode | Command | What it allows |
| --- | --- | --- |
| **Studio** | `c4 webapp <path>` | Browse, edit, save, create, rename and delete files. The default. |
| **Viewer** | `c4 webapp <path> --viewer` | Read-only. Routes that write DSL answer 403, so the guarantee holds against a crafted request, not just a hidden button. |

In both modes you can still arrange a diagram. Positions, routes and collapsed groups are per-user UI state, saved beside the model (see [Layout files](#layout-files)), never in it. Use `--viewer` for a kiosk, a demo or anything another person can reach.

> The Studio has no authentication and listens on `127.0.0.1` by default. It is built for one person on their own machine. You share models through git and the files c4studio generates.

## Editing

The source editor is a CodeMirror panel on the right of the diagram. Open it with the **Source** button in the top bar or the `e` key. *Show definition* on any element jumps straight to the line that declares it. A ● on the Source button marks unsaved work behind a closed editor.

- **Highlighting and autocomplete** for DSL keywords, your own element identifiers and your view keys, drawn from the loaded workspace.
- **Diagnostics as you type**, from the same parser the CLI uses. Invalid DSL still saves: an editor that refuses to save halfway through a thought gets in the way.
- **⌘S or Ctrl+S saves**, and the diagram redraws from the text.
- **Conflict detection.** If the file changed on disk after you opened it, the save stops and shows you both versions rather than overwriting.
- **A searchable file tree** covering every source under the root, including `!include` fragments. Right-click to create, rename or delete. **+ New** starts a workspace from a template.

The diagram is a preview of the text, never the other way round. c4studio never generates DSL from the model, so your comments, formatting and `!include` structure are always yours. Editing a file in another editor works too: the Studio reloads when the file changes.

## Working with the diagram

Every `systemLandscape`, `systemContext`, `container`, `component`, `dynamic` and `deployment` view renders as an interactive graph. The breadcrumb at the top left shows where you are. Double-click an element that has its own view to drill into it, and press `u` to go back up. `j` and `k` step through the views.

**Arranging.** Drag elements to place them. Shift-drag, or ⌘/Ctrl-click, selects several, and a toolbar appears to align or distribute them. The arrow keys nudge a selection by 1px, or 10px with Shift. **View ▾ › Snap** snaps to a grid. **Reset layout** returns a view to the automatic layout.

**Lines.** The toolbar switches every line between Bezier, Straight, Step and Smooth step. A Step or Smooth step line can be re-routed like a whiteboard elbow connector:

- drag the handle on a straight run to slide it sideways;
- double-click a run, or choose *Add step here* from the right-click menu, to add a jog;
- drag a line's end onto a side of its element to pin it there;
- drag a step flat to remove it. *Reset route* puts the line back.

A relationship style with `routing Orthogonal` is drawn with the same router, whatever the toolbar says.

**Expanding and collapsing.** The **+** on a container expands its components in place, without leaving the view. A group's boundary has a control to collapse it to a single box.

**Named layouts.** **Layouts ▾** saves the current arrangement of a view under a name, loads one back, or deletes one. Use it to keep a "for the board" and a "for the team" version of the same view.

**Details.** Select an element or a line and press `i`, or **Details**, for a card with its description, technology, tags, properties and relationships. An element with properties shows a small ⓘ badge. Click it to open the card.

**Hover and animation.** Hovering an element highlights its relationships. **View ▾ › Animate** (`a`) makes them march, which helps you follow a busy diagram. It respects your system's reduced-motion setting.

**Export.** **Export ▾** saves the view as PNG (`p`) or SVG (`s`), exactly as it looks on screen. For CI, use [`c4 render`](cli.html#c4-render) instead.

## Perspectives and impact

A **perspective** is a named annotation on elements and relationships: security, ownership, cost, anything. When a model has perspectives, the toolbar shows a picker. Choosing one fades everything that does not carry it, badges what does with its value, and switches the legend to those values. Colour comes from ordinary styles such as `element "Perspective:Security[value==High]"`. See [Perspectives](dsl-reference.html#9-perspectives) in the DSL reference.

**Impact analysis** answers "what else is involved if this changes?". Select an element, open its details with `i`, and choose **Show impact**. The view repaints: the element and whatever contains it are marked as changed, its dependents and dependencies get their own colours, and the rest fades. The card gives the counts across the whole model and the number of views that draw the element. The overlay stays on as you move between views. The same answer is available as [`c4 impact`](cli.html#c4-impact).

## Explorer, documentation and decisions

- **Explorer** draws the entire model as one graph, independent of any view, at the level you choose: systems, containers or components. Press `/` to search every element across every `!include` fragment. Its details panel lists the views an element appears in, so you can jump to them.
- **Documentation** and **Decisions** appear in the top bar when the workspace uses `!docs` and `!adrs`. They render the Markdown and the architecture decision records beside the model.

## Keyboard shortcuts

Press `?` in the Studio to see this list. These tables are generated from the same source as that overlay.

{{shortcuts}}

## Layout files

When you arrange a view, the Studio writes `<workspace>.layout.json` beside the workspace. It holds positions, sizes, line routes, dragged labels, expanded and collapsed elements, and named layouts.

- It is **per-user UI state**. Add `*.layout.json` to your `.gitignore`.
- `c4 render` and `c4 publish` honour it, so a rendered SVG matches what you arranged. Pass `--no-layout` for output that is identical on any machine.
- Sections are additive, so a file written by an older version still loads.

## The assistant (optional)

c4studio is local-first. Nothing it does reaches the network, with one exception that you have to switch on deliberately:

```bash
pip install 'c4studio[assistant]'
export ANTHROPIC_API_KEY=...
c4 webapp shop.dsl --assistant
```

Describe a change in words. The reply comes back as a **diff against your editor buffer**, which you apply or reject. Applying only changes the editor; nothing is written until you save.

**What leaves your machine:** the workspace source, including unsaved changes to the file you are editing. The panel lists exactly which files were sent. Without `--assistant`, the endpoint answers 403. The API key is read from the environment when it is used, and is never stored, logged or sent back.

## Dynamic perspectives

A perspective can carry a `url` instead of a value, and the Studio reads its value live from that address. This is **off by default**, because the addresses come from the workspace file and opening someone else's model would otherwise make your machine call their hosts. Turn it on with `c4 webapp <path> --dynamic-perspectives`. Only `http` and `https` are followed. Values refresh every 60 seconds, and a failed request shows its HTTP status rather than a stale value.
