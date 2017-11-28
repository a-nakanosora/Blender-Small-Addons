import bpy
import re

bl_info = {
    'name': 'Jump to Prev/Next Property Type',
    'description': 'Activate hotkeys - jump to prev/next property type',
    'author': 'A Nakanosora',
    'version': (0, 2, 1),
    'blender': (2, 6, 4),
    'location': 'Key (default: [F1]/[F2])',
    'category': 'UI'
}


class JumpPropertyTypeOperator(bpy.types.Operator):
    bl_idname = 'ui.jump_to_neighboring_property_type'
    bl_label = 'Jump to Prev/Next Property Type'

    mode = bpy.props.StringProperty(name='Direction', default='')

    def execute(self, context):
        if self.mode == 'PREV':
            jump_prop_type(-1)
        elif self.mode == 'NEXT':
            jump_prop_type(1)
        return {'FINISHED'}



def get_property_area():
    for n in bpy.context.screen.areas:
        if n.type == 'PROPERTIES':
            return n.spaces[0]
    return None

def get_available_types(prop_area):
    assert type(prop_area) is bpy.types.SpaceProperties

    ## <!> bulldozing method - get available types list through an error
    try:
        prop_area.context = '!!!CAUSE_ERROR!!!'
    except TypeError as e:
        error_msg_with_enum_info = e.__str__()

    ls_str = re.sub(r'^.*\((.+)\).*', r'[\1]', error_msg_with_enum_info)
    return eval(ls_str)

def jump_prop_type(offset=0):
    prop_area = get_property_area()
    if prop_area is None:
        return
    type_current = prop_area.context
    type_list = get_available_types(prop_area)
    idx = (type_list.index(type_current) + offset) % len(type_list)
    prop_area.context = type_list[idx]



def register():
    bpy.utils.register_class(JumpPropertyTypeOperator)

    wm = bpy.context.window_manager
    km = wm.keyconfigs.active.keymaps['Window']
    kmi = km.keymap_items.new(JumpPropertyTypeOperator.bl_idname, 'F2', 'PRESS', head=True)
    kmi.properties.mode = 'NEXT'
    kmi = km.keymap_items.new(JumpPropertyTypeOperator.bl_idname, 'F1', 'PRESS', head=True)
    kmi.properties.mode = 'PREV'

def unregister():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.active.keymaps['Window']
    for kmi in km.keymap_items[:]:
       if kmi.idname == JumpPropertyTypeOperator.bl_idname:
            km.keymap_items.remove(kmi)

    bpy.utils.unregister_class(JumpPropertyTypeOperator)



if __name__ == '__main__':
    register()
