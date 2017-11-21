'''
Blender Addon # Komb
'''

bl_info = {
    "name": "Komb",
    "description": "Quick make a mask image for composite",
    "author": "A Nakanosora",
    "version": (0, 1),
    "blender": (2, 7, 9),
    "location": "Node Editor > Compositing > Properties Panel > Komb",
    "category": 'Image'
    }


import bpy
import bgl
import gpu
from mathutils import Vector


class Pref:
    default_output_image_name = 'komb_output'
    use_pack_image_after_stop = True

class _State:
    def __init__(self):
        self.color = (1,1,1,1)
        self.reset()
    def reset(self):
        self.enabled = False
        self.lines = []
        self.current_line = None
        self.img_bake_target = None
State = _State()

def tautology(s):
    class _TautologyDict:
        def __setattr__(*args):
            raise Exception('tautology dict has only getters')
    dic = _TautologyDict()
    for n in s.strip().split():
        dic.__dict__[n] = n
    return dic

def get_center_pos(context):
    return Vector(( context.region.width/2 + context.space_data.backdrop_x
                  , context.region.height/2 + context.space_data.backdrop_y
                  ))
def get_zoom(context):
    return max(context.space_data.backdrop_zoom, .0001)


def make_throttle():
    import datetime
    def throttle(ms):
        ct = datetime.datetime.now().timestamp() * 1000
        if ct - throttle._t >= ms:
            throttle._t = ct
            return False
        return True
    throttle._t = 0
    return throttle
throttle = make_throttle()


def clear_image(img, color=(0,0,0,0)):
    img.source = 'GENERATED'
    img.generated_color = color

def remove_image(img):
    img.user_clear()
    bpy.data.images.remove(img)



def get_viewer_image():
    if 'Viewer Node' in bpy.data.images:
        img = bpy.data.images['Viewer Node']
        w,h = img.size[:]
        if w*h != 0:
            return img
    return None

def set_bake_target(context, img):
    context.window_manager.komb_bake_target = img
def get_bake_target(context):
    return context.window_manager.komb_bake_target

def get_brush_radius(context):
    return context.window_manager.komb_brush_radius
def get_brush_color(context):
    return context.window_manager.komb_brush_color
def swap_brush_colors(context):
    wm = context.window_manager
    wm.komb_brush_color, wm.komb_brush_color2 = wm.komb_brush_color2[:], wm.komb_brush_color[:]


def radius_falloff(x):
    return x
    #return x*x*(-2*x+3)
    #return (x*x*(-2*x+3) + x)/2



class KombLine:
    def __init__(self, color):
        self.color = color[:]
        self.seq = KombPointSequence()

class KombPointSequence:
    def __init__(self):
        self._kps = []
    def add(self, x,y,radius):
        self._kps.append(KombPoint(x,y,radius))
    def all(self, ):
        return self._kps.copy()

class KombPoint:
    def __init__(self, x,y,radius):
        self.x = x
        self.y = y
        self.radius = radius


class Komb_Operator(bpy.types.Operator):
    bl_idname = 'view3d.komb_operator'
    bl_label = 'Komb Operator'

    mode = bpy.props.StringProperty(default='')

    _handle_draw = None

    @classmethod
    def poll(cls, context):
        return context.area.type == 'NODE_EDITOR' and context.space_data.tree_type == 'CompositorNodeTree'

    def invoke(self, context, event):
        if self.mode=='START':
            img = get_viewer_image()
            if not img:
                self.report({'ERROR'}, '"Viewer Node" not found in image slot or zero size')
                return {'CANCELLED'}

            w,h = img.size[:]

            imgnodes = [n for n in [context.active_node]+context.selected_nodes if n and n.type=='IMAGE']
            if imgnodes:
                bimg = imgnodes[0].image
            elif Pref.default_output_image_name in bpy.data.images  \
                  and bpy.data.images[Pref.default_output_image_name].size[:] == (w,h):
                bimg = bpy.data.images[Pref.default_output_image_name]
            else:
                bimg = prepare_blimage(w, h, Pref.default_output_image_name)
                clear_image(bimg, (0,0,0,1))
            set_bake_target(context,bimg)
            State.img_bake_target = bimg

            State.enabled = True
            opt = {
                'image_size': (w,h)
                }
            self._handle_draw = bpy.types.SpaceNodeEditor.draw_handler_add(draw_callback, (self, context, opt), 'WINDOW', 'POST_PIXEL')
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        if self.mode=='EXIT':
            State.enabled = False
            return {'FINISHED'}

        if self.mode=='BAKE':
            img = get_viewer_image()
            if not img:
                self.report({'ERROR'}, '"Viewer Node" not found in image slot or zero size')
                return {'CANCELLED'}
            width, height = img.size[:]

            img = get_bake_target(context)
            if img:
                imgname = img.name
                render_offscreen(self, context, width, height, imgname)
                if State.img_bake_target is not None:
                    State.lines = []
                    State.current_line = None
                    State.img_bake_target.gl_free()
                    State.img_bake_target = bpy.data.images[imgname]
            return {'FINISHED'}

        self.report({'WARNING'}, 'invalid mode:'+self.mode)
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'ESC':
            State.enabled = False

        if not State.enabled:
            self.clean(context)
            context.area.tag_redraw()
            return {'FINISHED'}

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and event.ctrl:
                line = KombLine(get_brush_color(context))
                State.lines.append(line)
                State.current_line = line
                #return {'PASS_THROUGH'}
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE':
                State.current_line = None
                return {'PASS_THROUGH'}

        if event.type == 'MOUSEMOVE':
            if not throttle(1000/30) and State.current_line is not None:
                center = get_center_pos(context)
                zoom = get_zoom(context)
                p = Vector((event.mouse_region_x-center.x, event.mouse_region_y-center.y)) * (1/zoom)
                r = radius_falloff(event.pressure) * get_brush_radius(context)
                State.current_line.seq.add(p.x, p.y, r)
                context.area.tag_redraw()
                return {'PASS_THROUGH'}

        if event.type == 'X':
            if event.value=='RELEASE':
                swap_brush_colors(context)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.ctrl and event.type in {'Z', 'Y'}:
            return {'RUNNING_MODAL'}

        if context.area:
            context.area.tag_redraw()
        return {'PASS_THROUGH'}

    def clean(self, context):
        if self._handle_draw is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self._handle_draw, 'WINDOW')
            self._handle_draw = None

        if State.img_bake_target:
            State.img_bake_target.gl_free()
            if Pref.use_pack_image_after_stop and not State.img_bake_target.filepath:
                State.img_bake_target.pack(True)
        State.reset()


class Komb_ClearImageConfirm(bpy.types.Operator):
    bl_idname = 'view3d.komb_clearimage_confirm_dialog'
    bl_label = 'Clear Image?'
    bl_options = {'REGISTER', 'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if State.img_bake_target:
            clear_image(State.img_bake_target, (0,0,0,1))
        return {'FINISHED'}


class Komb_CreateImageDialog(bpy.types.Operator):
    bl_idname = "view3d.komb_createimg_dialog"
    bl_label = "Komb Create Image"
    bl_options = {'REGISTER', 'UNDO'}

    dialog_width = 250

    new_image_name = bpy.props.StringProperty()
    new_image_width = bpy.props.IntProperty(default=256)
    new_image_height = bpy.props.IntProperty(default=256)

    @classmethod
    def poll(cls, context):
        return context.area.type == 'NODE_EDITOR' and context.space_data.tree_type == 'CompositorNodeTree'

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label('create new image:')
        col.prop(self, 'new_image_name', text='Image Name')
        col.prop(self, 'new_image_width', text='Width')
        col.prop(self, 'new_image_height', text='Height')

    def invoke(self, context, event):
        img = get_viewer_image()
        if img:
            self.new_image_width, self.new_image_height = img.size[:]
        self.new_image_width = self.new_image_width or 256
        self.new_image_height = self.new_image_height or 256
        wm = context.window_manager
        wm.invoke_props_dialog(self, self.dialog_width)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        n = self.new_image_name
        w,h = self.new_image_width, self.new_image_height
        if not n or w*h==0:
            return {'CANCELLED'}
        img = bpy.data.images.new(n,w,h)

        ## create image node
        for sn in context.selected_nodes:
            sn.select = False
        imgnode = context.space_data.node_tree.nodes.new('CompositorNodeImage')
        imgnode.location = context.space_data.edit_tree.view_center
        imgnode.image = img
        return {'FINISHED'}

class Komb_Panel(bpy.types.Panel):
    bl_label = 'Komb'
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'

    @classmethod
    def poll(cls, context):
        return context.area.type == 'NODE_EDITOR' and context.space_data.tree_type == 'CompositorNodeTree'

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label('Komb:')

        if State.enabled:
            op = col.operator(Komb_Operator.bl_idname, text='Exit', icon='PAUSE')
            op.mode = 'EXIT'


            op = col.operator(Komb_Operator.bl_idname, text='Bake')
            op.mode = 'BAKE'
            col.prop(context.window_manager, 'komb_bake_target', text='Bake to')

            layout.separator()
            col = layout.column(align=True)
            col.operator(Komb_ClearImageConfirm.bl_idname, text='Clear Image')

            img = State.img_bake_target
            col.label('target: {}'.format(img.name if img else '(None)'))


            layout.separator()
            col = layout.column(align=True)
            col.prop(context.window_manager, 'komb_brush_radius', text='Brush Radius')
            row = col.row(align=True)
            row.prop(context.window_manager, 'komb_brush_color', text='')
            row.prop(context.window_manager, 'komb_brush_color2', text='')
        else:
            op = col.operator(Komb_Operator.bl_idname, text='Start', icon='PLAY')
            op.mode = 'START'

        layout.separator()
        col = layout.column(align=True)
        op = col.operator(Komb_CreateImageDialog.bl_idname, text='Create New Image')




def draw_callback(self, context, opt={}):
    center = opt.get('center') or get_center_pos(context)
    zoom = opt.get('zoom') or get_zoom(context)
    back_image_alpha = opt.get('back_image_alpha') or .5
    image_size = opt.get('image_size') or (0,0)
    width,height = image_size

    img = State.img_bake_target
    if img and width*height != 0:
        if not img.bindcode[0]:
            img.gl_load(0, bgl.GL_NEAREST, bgl.GL_NEAREST)
        else:
            img.gl_touch(0)

        bgl.glEnable(bgl.GL_BLEND)
        bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
        bgl.glBlendEquation(bgl.GL_FUNC_ADD)

        bgl.glEnable(bgl.GL_TEXTURE_2D)
        bgl.glColor4f(1,1,1,back_image_alpha)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, img.bindcode[0])

        bgl.glBegin(bgl.GL_QUADS)
        dw = Vector((width,0)) / 2
        dh = Vector((0,height)) / 2
        ps = [center+(-dw-dh)*zoom
             ,center+(dw-dh)*zoom
             ,center+(dw+dh)*zoom
             ,center+(-dw+dh)*zoom
             ]
        ts = [(0,0),(1,0),(1,1),(0,1)]
        for p,t in zip(ps,ts):
            bgl.glTexCoord2f(*t)
            bgl.glVertex2f(*p)
        bgl.glEnd()
        bgl.glDisable(bgl.GL_TEXTURE_2D)

    ##
    #bgl.glEnable(bgl.GL_BLEND)
    bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
    bgl.glBlendEquation(bgl.GL_FUNC_ADD)
    for line in State.lines:
        bgl.glColor4f(*(*line.color,1.0))

        ps = line.seq.all()
        if len(ps)<2:
            continue

        ka,kb = ps[0:2]
        a = Vector((ka.x,ka.y))
        b = Vector((kb.x,kb.y))
        t = (b-a).normalized()
        n = Vector((t.y, -t.x))
        prev_u = a+n*ka.radius
        prev_v = a-n*ka.radius

        for ka,kb in zip(ps[:-1], ps[1:]):
            a = Vector((ka.x,ka.y))
            b = Vector((kb.x,kb.y))
            t = (b-a).normalized()
            n = Vector((t.y, -t.x))
            u = b+n*kb.radius
            v = b-n*kb.radius
            bgl.glBegin(bgl.GL_QUADS)
            for p in [prev_u, u, v, prev_v]:
                bgl.glVertex2f(*(center+p*zoom))
            bgl.glEnd()
            prev_u = u
            prev_v = v

    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)
    bgl.glBlendEquation(bgl.GL_FUNC_ADD)


def render_offscreen(self, context, width, height, imgname=''):
    assert context.area.type == 'NODE_EDITOR' and context.space_data.tree_type == 'CompositorNodeTree'

    gos = gpu.offscreen.new(width,height)
    gos.bind(True)
    try:
        bgl.glMatrixMode(bgl.GL_PROJECTION)
        bgl.glLoadIdentity()
        bgl.glScalef(1/width*2,1/height*2,1.0)
        bgl.glTranslatef(-width/2,-height/2,0)

        draw_callback(self, context, {
                  'center': Vector((width/2, height/2))
                , 'zoom': 1.0
                , 'back_image_alpha': 1.0
                , 'image_size': (width, height)
                })

        buffer = bgl.Buffer(bgl.GL_FLOAT, width * height * 4)
        x,y = 0,0
        bgl.glReadPixels(x, y, width, height , bgl.GL_RGBA, bgl.GL_FLOAT, buffer)

        out = prepare_blimage(width, height, imgname or Pref.default_output_image_name)
        out.pixels = buffer[:]
    finally:
        gos.unbind(True)



def prepare_blimage(width, height, name='output'):
    if name in bpy.data.images:
        img = bpy.data.images[name]
        if img.size[:] != (width,height):
            img.scale(width,height)
    else:
        img = bpy.data.images.new(name, width, height)
    return img

def register():
    bpy.types.WindowManager.komb_bake_target = bpy.props.PointerProperty(type=bpy.types.Image)
    bpy.types.WindowManager.komb_brush_radius = bpy.props.FloatProperty(default=20.0, min=1.0, soft_max=200.0, step=100)
    bpy.types.WindowManager.komb_brush_color = bpy.props.FloatVectorProperty(name='Brush Color'
                                            , subtype='COLOR', default=[1.0,1.0,1.0])
    bpy.types.WindowManager.komb_brush_color2 = bpy.props.FloatVectorProperty(name='Brush Color 2'
                                            , subtype='COLOR', default=[0.0,0.0,0.0])
    bpy.utils.register_class(Komb_Operator)
    bpy.utils.register_class(Komb_ClearImageConfirm)
    bpy.utils.register_class(Komb_CreateImageDialog)
    bpy.utils.register_class(Komb_Panel)

def unregister():
    del bpy.types.WindowManager.komb_bake_target
    del bpy.types.WindowManager.komb_brush_radius
    del bpy.types.WindowManager.komb_brush_color
    del bpy.types.WindowManager.komb_brush_color2
    bpy.utils.unregister_class(Komb_Operator)
    bpy.utils.unregister_class(Komb_ClearImageConfirm)
    bpy.utils.unregister_class(Komb_CreateImageDialog)
    bpy.utils.unregister_class(Komb_Panel)


if __name__ == '__main__':
    register()
