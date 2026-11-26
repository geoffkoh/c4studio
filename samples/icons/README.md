Sample icons for the Studio's icon picker (PP-233), drawn for this repo.

- `basic/` is full-colour tiles, drawn as they are.
- `outline/` is one-colour glyphs, the kind a style tints to the box's
  text colour with `"c4studio.iconTint" "true"` (PP-234).
  `Cloud.svg` is drawn in `currentColor`, which is tinted without
  being asked (PP-239).

A real workspace keeps downloaded packs here instead — AWS Architecture
Icons, Font Awesome Free, Simple Icons — one folder per pack, committed
with the workspace. A style names a file relative to the DSL file:

    element "Function" {
        icon "icons/basic/Function_48.svg"
    }
