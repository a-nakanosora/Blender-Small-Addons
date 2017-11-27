bl_info = {
    'name': 'Render Path Auto Replacer',
    'description': 'Replace render output filepaths at rendering according to several syntaxes',
    'author': 'A Nakanosora',
    'version': (1, 3, 1),
    'blender': (2, 78, 0),
    'location': 'Render Settings > Output',
    'warning': '',
    'category': 'Render'
    }


import bpy
import re
from datetime import datetime as dt

class PrevPaths:
    scene = ''
    node_file_slot_base_paths = [] ## List< (target, path) >
    node_file_slot_paths = [] ## List< (target, path) >



##
def get_current_render_output(scene):
    return scene.render.filepath

def set_current_render_output(scene, p):
    scene.render.filepath = p

def get_current_filename():
    path = to_forwardslash(bpy.data.filepath)
    if not path:
        return None
    return re.findall(r'([^\/]+)\.blend$', path)[0]

def get_date_str():
    return dt.now().strftime('%Y%m%d')

def to_forwardslash(path):
    return path.replace('\\', '/')

def apply_path_macro(scene, path):
    ## $file, $scene, $camera
    filename = get_current_filename() or '_unsaved'+get_date_str()
    t = dt.now().timestamp()
    timestamp = '{:0.6f}'.format(t)
    time = str(int(t))
    path_next = path.replace('$file', filename)             \
                    .replace('$scene', scene.name)          \
                    .replace('$camera', scene.camera.name if scene.camera else '(camera none)')  \
                    .replace('$timestamp', timestamp)       \
                    .replace('$time', time)

    ## $(<var-name>)
    for n,v in get_defined_variables(scene):
        n2 = n.strip()
        v2 = v.strip()
        if n2:
            path_next = path_next.replace('$({})'.format(n2), v2)

    return path_next

def replace_paths(scene):
    p0 = get_current_render_output(scene)
    PrevPaths.scene = p0
    path_next = apply_path_macro(scene, p0)
    set_current_render_output(scene, path_next)

    for n in scene.node_tree.nodes:
        if n.type == 'OUTPUT_FILE':
            PrevPaths.node_file_slot_base_paths.append( (n, n.base_path) )
            n.base_path = apply_path_macro(scene, n.base_path)

            for fs in n.file_slots:
                PrevPaths.node_file_slot_paths.append( (fs, fs.path) )
                fs.path = apply_path_macro(scene, fs.path)

def restore_paths(scene):
    set_current_render_output(scene, PrevPaths.scene)

    for target, path in PrevPaths.node_file_slot_base_paths:
        target.base_path = path

    for target, path in PrevPaths.node_file_slot_paths:
        target.path = path

    PrevPaths.scene = ''
    PrevPaths.node_file_slot_base_paths = []
    PrevPaths.node_file_slot_paths = []






#####
## List UI
class RPAutoRep_PropGroup(bpy.types.PropertyGroup):
    name = bpy.props.StringProperty()
    value = bpy.props.StringProperty()

bpy.utils.register_class(RPAutoRep_PropGroup) ## <!>

class RPAutoRep_CollectionProperty(bpy.types.PropertyGroup):
    active_index = bpy.props.IntProperty()
    macrovar_list = bpy.props.CollectionProperty(type=RPAutoRep_PropGroup)

    def add(self):
        item = self.macrovar_list.add()
        item.name = "name"
        item.value = "value"
        self.active_index = len(self.macrovar_list)-1

    def remove(self):
        if len(self.macrovar_list):
            self.macrovar_list.remove(self.active_index)
            if len(self.macrovar_list)-1 < self.active_index:
                self.active_index = len(self.macrovar_list)-1
                if self.active_index < 0:
                    self.active_index = 0

    def move(self, index1, index2):
        if len(self.macrovar_list) < 2:
            return
        if 0 <= index1 < len(self.macrovar_list):
            if 0 <= index2 < len(self.macrovar_list):
                self.macrovar_list.move(index1, index2)
                self.active_index = index2

class RPAutoRep_AddItemOperator(bpy.types.Operator):
    bl_idname = "render.renderpathautoreplace_add_item"
    bl_label = "Add Item"

    def execute(self, context):
        context.scene.render_path_macro_ui_list.add()
        return {'FINISHED'}

class RPAutoRep_RemoveItemOperator(bpy.types.Operator):
    bl_idname = "render.renderpathautoreplace_remove_item"
    bl_label = "Remove Item"

    def execute(self, context):
        context.scene.render_path_macro_ui_list.remove()
        return {'FINISHED'}

class RPAutoRep_MoveItemOperator(bpy.types.Operator):
    bl_idname = "render.renderpathautoreplace_move_item"
    bl_label = "Move Item"

    type = bpy.props.StringProperty(default='UP')

    def execute(self, context):
        ui_list = context.scene.render_path_macro_ui_list
        if self.type == 'UP':
            ui_list.move(ui_list.active_index, ui_list.active_index-1)
        elif self.type == 'DOWN':
            ui_list.move(ui_list.active_index, ui_list.active_index+1)
        return {'FINISHED'}

class RPAutoRep_GroupList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            a = layout.row()
            a.scale_x = 0.05
            a.label('  ')

            layout.prop(item, "name", text="", emboss=False, icon_value=icon)

            b = layout.row()
            b.scale_x = 0.1
            b.label('=')

            layout.prop(item, "value", text="", emboss=False, icon_value=icon)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

def render_panel(self, context):
    layout = self.layout
    #layout = layout.box()

    layout.row().label('Render Path Replacer Variables:')

    row = layout.row()
    ui_list = context.scene.render_path_macro_ui_list
    row.template_list("RPAutoRep_GroupList", "", ui_list, "macrovar_list", ui_list, "active_index", rows=1)

    col = row.column(align=True)
    col.operator(RPAutoRep_AddItemOperator.bl_idname, icon='ZOOMIN', text="")
    col.operator(RPAutoRep_RemoveItemOperator.bl_idname, icon='ZOOMOUT', text="")
    col.operator(RPAutoRep_MoveItemOperator.bl_idname, icon='TRIA_UP', text="").type = 'UP'
    col.operator(RPAutoRep_MoveItemOperator.bl_idname, icon='TRIA_DOWN', text="").type = 'DOWN'

def get_defined_variables(scene):
    ui_list = scene.render_path_macro_ui_list
    mvars = []
    for mvar in ui_list.macrovar_list:
        mvars.append( (mvar.name, mvar.value) )
    return mvars



########
##
@bpy.app.handlers.persistent
def onrender_before(scene):
    replace_paths(scene)

@bpy.app.handlers.persistent
def onrender_after(scene):
    restore_paths(scene)
    pass



def register():
    bpy.app.handlers.render_init.append(onrender_before)
    bpy.app.handlers.render_complete.append(onrender_after)
    bpy.app.handlers.render_cancel.append(onrender_after)

    bpy.utils.register_class(RPAutoRep_AddItemOperator)
    bpy.utils.register_class(RPAutoRep_RemoveItemOperator)
    bpy.utils.register_class(RPAutoRep_MoveItemOperator)
    try:
        bpy.utils.register_class(RPAutoRep_PropGroup)
    except:pass
    bpy.utils.register_class(RPAutoRep_GroupList)
    bpy.utils.register_class(RPAutoRep_CollectionProperty)
    bpy.types.RENDER_PT_output.append(render_panel)
    bpy.types.Scene.render_path_macro_ui_list = bpy.props.PointerProperty(type=RPAutoRep_CollectionProperty)

def unregister():
    bpy.app.handlers.render_init.remove(onrender_before)
    bpy.app.handlers.render_complete.remove(onrender_after)
    bpy.app.handlers.render_cancel.remove(onrender_after)

    bpy.utils.unregister_class(RPAutoRep_AddItemOperator)
    bpy.utils.unregister_class(RPAutoRep_RemoveItemOperator)
    bpy.utils.unregister_class(RPAutoRep_MoveItemOperator)
    bpy.utils.unregister_class(RPAutoRep_PropGroup)
    bpy.utils.unregister_class(RPAutoRep_GroupList)
    bpy.utils.unregister_class(RPAutoRep_CollectionProperty)
    bpy.types.RENDER_PT_output.remove(render_panel)
    del bpy.types.Scene.render_path_macro_ui_list



if __name__ == '__main__':
    register()
