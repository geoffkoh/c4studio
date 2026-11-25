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
- **Find and replace** with ⌘/Ctrl-F in the editor, including matches far below what is on screen, which the browser's own find cannot reach. Enter steps to the next match, Shift-Enter to the previous one, and other occurrences of the selected text are highlighted.
- **Diagnostics as you type**, from the same parser the CLI uses. Invalid DSL still saves: an editor that refuses to save halfway through a thought gets in the way.
- **⌘S or Ctrl+S saves**, and the diagram redraws from the text.
- **Conflict detection.** If the file changed on disk after you opened it, the save stops and shows you both versions rather than overwriting.
- **A searchable file tree** covering every source under the root, including `!include` fragments. Right-click to create, rename or delete. **+ New** starts a workspace from a template.

The diagram is a preview of the text, never the other way round. c4studio never generates DSL from the model, so your comments, formatting and `!include` structure are always yours. Editing a file in another editor works too: the Studio reloads when the file changes.

## Working with the diagram

Every `systemLandscape`, `systemContext`, `container`, `component`, `dynamic` and `deployment` view renders as an interactive graph. The breadcrumb at the top left shows where you are. Double-click an element that has its own view to drill into it, and press `u` to go back up. `j` and `k` step through the views.

**Arranging.** Drag elements to place them. Shift-drag, or ⌘/Ctrl-click, selects several, and a toolbar appears to align or distribute them. The arrow keys nudge a selection by 1px, or 10px with Shift. **View ▾ › Snap** snaps to a grid. Select an element or a boundary to resize it by its handles. A box cannot be made smaller than its own text, so a narrower box wraps its text more tightly. **Reset layout** returns a view to the automatic layout, sizes included.

**Lines.** The toolbar switches every line between Bezier, Straight, Step and Smooth step. The choice is saved per view in the layout file, so `c4 render`, `c4 publish` and the VS Code preview draw the same lines. A view you have not chosen for uses the style you picked last. A Step or Smooth step line can be re-routed like a whiteboard elbow connector:

- drag the handle on a straight run to slide it sideways;
- double-click a run, or choose *Add step here* from the right-click menu, to add a jog;
- drag a line's end onto a side of its element to pin it there;
- drag a step flat to remove it. *Reset route* puts the line back.

A relationship style with `routing Orthogonal` is drawn with the same router, whatever the toolbar says.

**Expanding and collapsing.** The **+** on a container expands its components in place, without leaving the view. A group's boundary has a control to collapse it to a single box. Lines between the group's members and the same element then merge into one. If their descriptions differ, the line reads `3 relationships [1]`, and the legend lists what `[1]` stands for, one relationship per line. The key is part of the legend, so it is in exported images and `c4 render` output too. Selecting a merged line shows the same list in the details card.

**Named layouts.** **Layouts ▾** saves the current arrangement of a view under a name, loads one back, or deletes one. Use it to keep a "for the board" and a "for the team" version of the same view.

**Details.** Select an element or a line and press `i`, or **Details**, for a card with its description, technology, tags, properties and relationships. An element with properties shows a small ⓘ badge. Click it to open the card. Under **Styled by**, the card names every style that paints the selection, in the order they apply: where two set the same property, the later wins. Click a style written in your files to open the editor at it. A style marked *theme* comes from a theme and has no line to open.

**Changing colours.** In the Studio, **Edit style** beside *Styled by* opens colour pickers: background, text and border for a box; colour and dash pattern for a line. Each row says where the value comes from now: *from Database*, *theme* or *default*. A change is written to the workspace's `styles` block, so teammates, `c4 render` and Structurizr all see it. The layout file never holds a colour. Before you pick, choose which boxes change:

- **All "Database" (3)** edits the style for the element's most specific tag, and the count says how many elements across the model carry it. If your files have no style for that tag yet, one is added after the others.
- **Only this** gives the element a tag of its own (its name) and a style for it. Picking again later reuses that tag.

The diagram repaints as you drag; the DSL is written when the picker closes, through the same save as the editor. If the file has unsaved edits, the change joins them in the editor instead, for you to save. **×** on a row set by the style being edited removes that line. Viewer mode does not offer any of this.

**Your logo.** A style for the tag `Workspace:Icon` sets the workspace's logo, which no element needs to carry: `element "Workspace:Icon" { icon "brand/logo.svg" }`. It appears before every diagram's title, in exports and `c4 render` too, and before the workspace's name in the top bar.

To choose it, open the details card with nothing selected. Its **Workspace** row shows the logo; click it, or click the logo on a diagram's title. The picker lists the images in the workspace's folder, those in `brand/` or named like a logo first, and a search reaches the rest. Build output and files your `.gitignore` excludes are left out, since a logo the repository does not hold would vanish for the next person. The arrow keys preview the focused image on the title; **Enter**, a double click or **Use** writes the `Workspace:Icon` style. **Choose a file…** takes one from elsewhere on your machine: the picker names where it will copy it, `brand/<name>`, and copies only when you confirm. If the workspace already holds the same file, it is used where it is. A logo is embedded in every export, so it can be at most 256 KB. The row's **×** removes the logo, with **Undo**. A workspace that still sets `branding { logo }`, which is no longer drawn, is offered that logo with **Use it**.

**Icons and logos.** The same card's **Icon** row puts an image above the element's name: an AWS service, a database, a vendor's logo. Icons come from an `icons/` folder beside the workspace, which you fill by downloading a pack and unzipping it there, one folder per pack: [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/), [Font Awesome Free](https://fontawesome.com/download) or [Simple Icons](https://simpleicons.org/), for example. Commit the folder with the workspace. The Studio never downloads anything itself. It does ship one pack, the outline set of [Tabler Icons](https://tabler.io/icons) (MIT, about 4,800 icons, without Tabler's brand logos), listed beside your own as **tabler**: using one copies it into `icons/tabler/` beside the workspace, with Tabler's licence, so the DSL names a file in your repository and works without c4studio. Tabler icons are drawn in the box's text colour. Opening the row widens the card into an icon browser, and if the box is under it the diagram slides it into view beside the card, sliding back when you close the browser unless you moved the diagram yourself. Before you type, it shows the icons the workspace already uses, the ones you used recently, and suggestions grouped by the role a box plays (people, apps, services, data, messaging, infrastructure). With room, a list down the left lets you go through a pack, or one of Tabler's categories; on a narrower canvas the list becomes a **Show** menu. Search matches the start of words in an icon's name, tags and category, and knows the shorthand architects use: `db` finds databases, `k8s`, `mq` and `fn` work too. Icons matching the word you typed come before those matching only its shorthand. Variants are folded under their icon, so `message` shows one tile and a **+N variants** tile that opens `message-x`, `message-off` and the rest in place. Each icon appears once, however many sizes and formats the pack ships it in, and every result is a scroll away rather than cut off. The arrow keys preview the focused icon on the diagram, and in a strip at the bottom drawn on the box's own colours. **Enter**, a double click or **Use** writes it, and **Esc** goes back with nothing changed. **Path or URL…** at the bottom takes an image from elsewhere in the repository or an `https://` address instead. It is written as `icon "icons/aws/Arch_AWS-Lambda_48.svg"` in the style, relative to the file the style is in, with the same *All* / *Only this* choice as colours. The image is embedded when the DSL is read, so it shows in `c4 render`, `c4 publish` and the VS Code preview too. See [`icon`](dsl-reference.html) in the DSL reference.

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
