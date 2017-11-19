'''
save active viewport as an image file considering OpenGL draw callbacks
'''

bl_info = {
    "name": "OpenGL Render Plan B",
    "description": "save active viewport as an image file considering OpenGL draw callbacks",
    "author": "nk",
    "version": (0, 1, 2),
    "blender": (2, 7, 9),
    "location": "3D View > Header",
    "category": '3D View'
    }



import bpy
import bgl
import re

class Pref:
    blimgname = 'Viewport Render Result'


#class OGLRPlB_Panel(bpy.types.Panel):
class OGLRPlB_Panel(bpy.types.Header):
    bl_label = "OpenGl Render Plan B"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "Relations"
    bl_idname = 'view3d.oglplb_panel'
    bl_context = 'objectmode'

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.alignment = 'RIGHT'
        row.label('PlanB:')

        row2 = row.row(align=True)
        row2.active = context.space_data.region_3d.view_perspective == 'CAMERA'
        op = row2.operator(OGLRPlB_Operator.bl_idname, text='', icon='CURSOR')
        op.mode = 'CENTER_CAMERA_VIEW'

        op = row.operator(OGLRPlB_Operator.bl_idname, text='', icon='RENDER_STILL')
        op.mode = 'RENDER'
        op = row.operator(OGLRPlB_Operator.bl_idname, text='', icon='RENDER_ANIMATION')
        op.mode = 'RENDER_ANIM'

class OGLRPlB_Operator(bpy.types.Operator):
    bl_idname = 'view3d.oglplb_operator'
    bl_label = 'OpenGl Render Plan B'

    mode = bpy.props.StringProperty(default = "")
    _frame = -1
    _rendering = False
    _rendered = {}
    _timer = None

    def execute(self, context):
        wm = context.window_manager

        if self.mode == 'CENTER_CAMERA_VIEW':
            center_cameraview(context)

        elif self.mode == 'RENDER':
            render_viewport(context, save_image_as_file=False, show_image=True)

        elif self.mode == 'RENDER_ANIM':
            if Pref.blimgname in bpy.data.images:
                ## <!> remove before rendering to avoid scene update bug
                bpy.data.images.remove(bpy.data.images[Pref.blimgname])

            context.scene.frame_current = context.scene.frame_start
            self._frame = -1
            self._rendering = False
            self._rendered = {}
            self._timer = wm.event_timer_add(1.0/60, context.window)
            wm.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        return {'FINISHED'}


    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        if event.type in {'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}

        elif event.type == 'TIMER':
            fr = context.scene.frame_current
            if fr > context.scene.frame_end:
                context.scene.frame_current = context.scene.frame_end
                self.cancel(context)
                return {'FINISHED'}
            elif self._rendering:
                return {'PASS_THROUGH'}
            elif fr in self._rendered:
                context.scene.frame_current += 1
                return {'PASS_THROUGH'}
            elif self._frame != fr:
                self._rendering = True
                render_viewport(context, save_image_as_file=True, show_image=False)
                self._rendering = False
                self._rendered[fr] = True
                self._frame = fr
                return {'PASS_THROUGH'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self._timer = None
        context.area.tag_redraw()

def render_viewport(context, save_image_as_file=False, show_image=False):
    region = context.region
    x = region.x
    y = region.y
    width = region.width
    height = region.height

    out = prepare_blimage(width, height, Pref.blimgname)

    buffer = bgl.Buffer(bgl.GL_FLOAT, width * height * 4)
    bgl.glReadPixels(x, y, width, height , bgl.GL_RGBA, bgl.GL_FLOAT, buffer)
    out.pixels = buffer[:]

    if save_image_as_file:
        save_image(out, context.scene)

    if show_image:
        def set_imageeditor_image():
            win = context.window
            for area_imeditor in [area for area in win.screen.areas if area.type == 'IMAGE_EDITOR']:
                for s in [s for s in area_imeditor.spaces if s.type=='IMAGE_EDITOR']:
                    s.image = out
                    return
        set_imageeditor_image()

def prepare_blimage(width, height, name='output'):
    if name in bpy.data.images:
        img = bpy.data.images[name]
        if img.size[:] != (width,height):
            img.scale(width,height)
    else:
        img = bpy.data.images.new(name, width, height)
    return img

def register():
    bpy.utils.register_class(OGLRPlB_Panel)
    bpy.utils.register_class(OGLRPlB_Operator)

def unregister():
    bpy.utils.unregister_class(OGLRPlB_Panel)
    bpy.utils.unregister_class(OGLRPlB_Operator)


def forwardslash(path):
    path = re.sub(r'\\', '/', path)
    path = re.sub(r'/+', '/', path)
    return path

def gen_savedest_imagepath(scene, index):
    return forwardslash('{}/{}.{}'.format( bpy.path.abspath(scene.render.filepath)
                                         , ('0000'+str(index))[-4:]
                                         , scene.render.image_settings.file_format.lower()
                                         ))
def save_image(image, scene, index=None):
    if index is None:
        index = scene.frame_current
    path = gen_savedest_imagepath(scene, index)
    image.save_render(path, scene)
    print('Saved: '+path)

def center_cameraview(context):
    r3d = context.space_data.region_3d
    if r3d.view_perspective == 'CAMERA':
        r3d.view_camera_offset=(0,0)



if __name__ == "__main__":
    register()
