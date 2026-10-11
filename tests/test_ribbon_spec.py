import unittest

from mmclone.ui import ribbon_spec as rs


def walk_widgets(tab):
    """Yield every Button, Spin and Gallery in a tab."""
    for group in tab.groups:
        for slot in group.slots:
            if isinstance(slot, rs.SmallColumn):
                yield from slot.items
            else:
                yield slot


class RibbonSpecTests(unittest.TestCase):
    def test_tab_order_and_contextual_tab(self):
        self.assertEqual([t.id for t in rs.TABS],
                         ["home", "animations", "effects", "project", "view", "edit"])
        self.assertEqual([t.id for t in rs.TABS if t.contextual], ["edit"])
        self.assertEqual(rs.EDIT.contextual, "Video Tools")

    def test_all_ids_are_unique(self):
        ids = []
        for tab in rs.TABS:
            for widget in walk_widgets(tab):
                ids.append(widget.id)
                if isinstance(widget, rs.Button):
                    ids.extend(m.id for m in widget.menu)
        self.assertEqual(len(ids), len(set(ids)), "duplicate command ids")

    def test_buttons_have_text_and_icons(self):
        for tab in rs.TABS:
            for widget in walk_widgets(tab):
                if isinstance(widget, rs.Button):
                    self.assertTrue(widget.text.strip(), widget.id)
                    self.assertTrue(widget.icon.startswith("mdi6."), widget.id)

    def test_requires_values_are_valid(self):
        for tab in rs.TABS:
            for widget in walk_widgets(tab):
                self.assertIn(getattr(widget, "requires", None), (None, "clips", "selection"),
                              widget.id)

    def test_galleries_are_well_formed(self):
        for tab in rs.TABS:
            for widget in walk_widgets(tab):
                if isinstance(widget, rs.Gallery):
                    self.assertGreaterEqual(len(widget.items), widget.visible, widget.id)
                    item_ids = [i.id for i in widget.items]
                    self.assertEqual(len(item_ids), len(set(item_ids)), widget.id)

    def test_is_enabled(self):
        self.assertTrue(rs.is_enabled(None, False, False))
        self.assertFalse(rs.is_enabled("clips", False, False))
        self.assertTrue(rs.is_enabled("clips", True, False))
        self.assertFalse(rs.is_enabled("selection", True, False))
        self.assertTrue(rs.is_enabled("selection", True, True))

    def test_expected_movie_maker_commands_exist(self):
        wanted = {"home.paste", "home.add_media", "home.add_music", "home.webcam",
                  "home.narration", "home.snapshot", "home.title", "home.caption",
                  "home.credits", "home.rotate_left", "home.rotate_right", "home.remove",
                  "home.select_all", "home.save_movie", "project.aspect", "view.zoom_in",
                  "view.zoom_out", "view.zoom_reset", "view.thumbnail_size",
                  "view.fullscreen", "view.waveforms", "edit.split", "edit.trim",
                  "edit.set_start", "edit.set_end", "edit.stabilize", "edit.speed",
                  "edit.volume", "edit.fade_in", "edit.fade_out", "fx.brightness",
                  "anim.transition", "anim.pan_zoom", "fx.effect"}
        have = {w.id for tab in rs.TABS for w in walk_widgets(tab)}
        self.assertEqual(wanted - have, set())

    def test_save_movie_menu_matches_presets(self):
        home_buttons = {w.id: w for w in walk_widgets(rs.HOME) if isinstance(w, rs.Button)}
        menu_ids = [m.id for m in home_buttons["home.save_movie"].menu]
        self.assertEqual(menu_ids, [f"file.save_movie/{p.id}" for p in rs.EXPORT_PRESETS])

    def test_brightness_has_a_preset_menu(self):
        effects_buttons = {w.id: w for w in walk_widgets(rs.EFFECTS) if isinstance(w, rs.Button)}
        menu_ids = [m.id for m in effects_buttons["fx.brightness"].menu]
        self.assertEqual(menu_ids, ["fx.brightness.darker2", "fx.brightness.darker1",
                                    "fx.brightness.normal", "fx.brightness.brighter1",
                                    "fx.brightness.brighter2"])

    def test_trim_tool_is_checkable(self):
        home_buttons = {w.id: w for w in walk_widgets(rs.EDIT) if isinstance(w, rs.Button)}
        self.assertTrue(home_buttons["edit.trim"].checkable)

    def test_edit_tab_needs_a_selection(self):
        for widget in walk_widgets(rs.EDIT):
            self.assertEqual(widget.requires, "selection", widget.id)


if __name__ == "__main__":
    unittest.main()
