
bl_info = {
    'name': 'Bl Console History Menu',
    'description': 'Show console history menu',
    'author': 'A Nakanosora',
    'version': (0, 1),
    'blender': (2, 79),
    'location': 'Console > [F3] key',
    'category': 'Console',
}

import bpy


class DefaultPref:
    lines_limit_size = 100
    clear_line_before_paste = False


class BlConsoleHistoryMenu_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    lines_limit_size = bpy.props.IntProperty(name='Lines Limit Size', default=DefaultPref.lines_limit_size, min=1)
    clear_line_before_paste = bpy.props.BoolProperty(name='Clear Line Before Paste', default=DefaultPref.clear_line_before_paste)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'lines_limit_size')
        layout.prop(self, 'clear_line_before_paste')


def get_pref(context):
    addon_prefs = context.user_preferences.addons[__name__].preferences  \
                    if __name__ and __name__ in context.user_preferences.addons  \
                    else DefaultPref
    return addon_prefs


class BlConsoleHistoryMenu(bpy.types.Operator):
    bl_idname = 'console.blconsole_history_menu'
    bl_label = 'Console History'
    bl_options = {'REGISTER'}
    bl_property = 'item'

    def get_search_items(self, context):
        items = []
        prev = ''
        lines_limit_size = get_pref(context).lines_limit_size
        #for item in ['a','b','c']:
        #for h in reversed(context.space_data.history):
        for h in reversed(context.space_data.history[:-1][-lines_limit_size:]): ## `[:-1]` -- omit current input
            item = h.body
            if not item:
                continue
            if item == prev:
                continue
            items.append((item, item, ""))
            prev = item
        return items

    item = bpy.props.EnumProperty(items = get_search_items)

    @classmethod
    def poll(cls, context):
        return context.area.type == 'CONSOLE'

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"CANCELLED"}

    def execute(self, context):
        s = self.item
        if get_pref(context).clear_line_before_paste:
            bpy.ops.console.clear_line(context.copy())
        bpy.ops.console.insert(context.copy(), text=s)
        return {"FINISHED"}


##
addon_keymaps = []

def register():
    bpy.utils.register_class(BlConsoleHistoryMenu)
    bpy.utils.register_class(BlConsoleHistoryMenu_AddonPreferences)
    ##
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Console', space_type='CONSOLE')
    kmi = km.keymap_items.new(BlConsoleHistoryMenu.bl_idname, 'F3', 'PRESS')
    addon_keymaps.append(km)

def unregister():
    bpy.utils.unregister_class(BlConsoleHistoryMenu)
    bpy.utils.unregister_class(BlConsoleHistoryMenu_AddonPreferences)
    ##
    wm = bpy.context.window_manager
    for km in addon_keymaps:
        for kmi in km.keymap_items[:]:
           if kmi.idname == BlConsoleHistoryMenu.bl_idname:
                km.keymap_items.remove(kmi)
        wm.keyconfigs.addon.keymaps.remove(km)
    addon_keymaps.clear()


if __name__ == "__main__":
    register()
