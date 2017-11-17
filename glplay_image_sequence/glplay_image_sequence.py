'''
Blender Addon # GL Play Image Sequence
'''


bl_info = {
    "name": "GL Play Image Sequence",
    "description": "Play Image Sequence on Viewport playback",
    "author": "A Nakanosora",
    "version": (0, 3, 1),
    "blender": (2, 7, 9),
    "location": "3D View > Properties Panel > GLPlay Image Sequence",
    "category": '3D View'
    }


import bpy
import bgl
from mathutils import Vector


class Pref:
    use_normalized_size = True
    #use_normalized_size = False

    use_centering_origin = True
    #use_centering_origin = False

    #use_alpha_clip = True
    use_alpha_clip = False

class State:
    frame = -1
    glplay_objs = []
    glplay_texs = []
    playing = False
    do_clean = None

def tautology(s):
    class _TautologyDict:
        def __setattr__(*args):
            raise Exception('tautology dict has only getters')
    dic = _TautologyDict()
    for n in s.strip().split():
        dic.__dict__[n] = n
    return dic

BlendMode = tautology('''
    ALPHAOVER
    ADDITIVE
''')

class GLTexture():
    def __init__(self, image, frame, frame_offset=0, blendmode=BlendMode.ALPHAOVER):
        self.image = image
        self.width = 0
        self.height = 0
        self._validframerange = -1,-1
        self._lastframe = -1
        self.frame_offset = frame_offset
        self.blendmode = blendmode

        self.load_image(image, frame)

    def load_image(self, image, frame):
        assert(type(image) == bpy.types.Image)
        self.image = image
        self.width, self.height = self.image.size

        self._validframerange = get_sequence_valid_frame_range(image)
        if not self.is_valid_on(frame):
            frame = self._validframerange[0]-self.frame_offset

        self.reload(frame)

    def reload(self, frame):
        if self.is_valid_on(frame):
            self.image.gl_free()
            self.image.gl_load(frame+self.frame_offset, bgl.GL_NEAREST, bgl.GL_NEAREST)
            self._lastframe = frame+self.frame_offset

    def touch(self):
        self.image.gl_touch(self._lastframe)

    def free(self):
        self.image.gl_free()

    def is_valid_on(self, frame):
        a,b = self._validframerange
        return a<=(frame+self.frame_offset)<b

    def bind(self):
        if self.image.bindcode[0]:
            bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.image.bindcode[0])
        else:
            self.reload(self._lastframe)


def get_sequence_valid_frame_range(image):
    '''
    @return (frame1, frame2)
        -- `image.gl_load(frame)` will success at frame1 <= frame < frame2
    '''
    ## #temp
    assert(type(image) == bpy.types.Image)
    if image.source != 'SEQUENCE':
        return (1,2)
    def tryload(frame):
        try:
            image.gl_load(frame)
            image.gl_free()
            return True
        except RuntimeError:
            return False

    limit = 500
    a = 1
    while not tryload(a):
        if a>limit:
            raise Exception('get_sequence_valid_frame_range Error: cannot get first valid frame')
        a+=1
    first = a

    b = first+1
    while tryload(b):
        b += 100

    aa = first
    while b-aa>1:
        c = (aa+b)//2
        if tryload(c):
            aa = c
        else:
            b = c
    return (first,b)

def create_mesh_obj(scene, width, height):
    NAME = 'glplay plane'
    mesh = bpy.data.meshes.new(NAME)
    mesh.vertices.add(4)
    for i,p in enumerate([(0,0,0), (width,0,0), (width,height,0), (0,height,0)]):
        mesh.vertices[i].co = p
    mesh.edges.add(4)
    for i,p in enumerate([(0,1), (1,2), (2,3), (3,0)]):
        mesh.edges[i].vertices = p
    obj = bpy.data.objects.new(NAME, mesh)
    scene.objects.link(obj)
    return obj



def draw_callback(self, context):

    bgl.glColor4f(1.0, 1.0, 1.0, 1.0)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_TEXTURE_2D)

    if Pref.use_alpha_clip:
        bgl.glAlphaFunc(bgl.GL_GREATER, 0.1)
        bgl.glEnable(bgl.GL_ALPHA_TEST)

    texcos = [(0.,0.), (1.,0.), (1.,1.), (0.,1.)]

    ## z-sort
    viewloc = context.space_data.region_3d.view_matrix.inverted().translation
    ots = [((obj.location-viewloc).length, obj, tex) for obj,tex in zip(State.glplay_objs, State.glplay_texs)]
    ots = sorted(ots, reverse=True)

    fr = context.scene.frame_current
    for l,obj,tex in ots:
        ps = [obj.matrix_world*v.co for v in obj.data.vertices[0:4]]
        if tex.blendmode == BlendMode.ALPHAOVER:
            bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
            bgl.glBlendEquation(bgl.GL_FUNC_ADD)
        elif tex.blendmode == BlendMode.ADDITIVE:
            bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE)
            bgl.glBlendEquation(bgl.GL_FUNC_ADD)
        tex.bind()
        bgl.glBegin(bgl.GL_QUADS)
        for p,t in zip(ps, texcos):
            bgl.glTexCoord2f(*t)
            bgl.glVertex3f(*p)
        bgl.glEnd()

    bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
    bgl.glBlendEquation(bgl.GL_FUNC_ADD)
    bgl.glDisable(bgl.GL_TEXTURE_2D)
    bgl.glDisable(bgl.GL_BLEND)
    if Pref.use_alpha_clip:
        bgl.glDisable(bgl.GL_ALPHA_TEST)


class GLPlay_Operator(bpy.types.Operator):
    bl_idname = "view3d.glplay_operator"
    bl_label = "GL Play Operator"

    mode = bpy.props.StringProperty(default='')

    _handle_draw = None
    _on_frame_change = None

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def modal(self, context, event):
        if event.type == 'ESC':
            State.playing = False

        if not State.playing:
            self.clean(context)
            context.area.tag_redraw()
            #return {'CANCELLED'}
            return {'PASS_THROUGH'}

        if context.area:
            context.area.tag_redraw()
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if self.mode == 'PLAY':
            if State.playing:
                #self.clean(context)
                self.report({'WARNING'}, 'playing')
                return {'FINISHED'}

            if context.area.type == 'VIEW_3D':
                frame = context.scene.frame_current
                State.frame = frame
                State.glplay_objs = [obj for obj in context.scene.objects if obj.glplay_image and not obj.hide]
                State.glplay_texs = [GLTexture(obj.glplay_image, frame, obj.glplay_image_offset_frame, obj.glplay_blendmode) for obj in State.glplay_objs]

                self._handle_draw = bpy.types.SpaceView3D.draw_handler_add(draw_callback, (self, context), 'WINDOW', 'POST_VIEW')
                State.playing = True

                def on_frame_change(scene):
                    frame = scene.frame_current
                    if State.frame != frame:
                        State.frame = frame
                        for tex in State.glplay_texs:
                            tex.reload(frame)
                            tex.touch()
                self._on_frame_change = on_frame_change
                bpy.app.handlers.frame_change_pre.append(self._on_frame_change)

                context.area.tag_redraw()
                context.window_manager.modal_handler_add(self)

                def do_clean():
                    self.clean(context)
                State.do_clean = do_clean
                return {'RUNNING_MODAL'}
            else:
                self.report({'WARNING'}, 'View3D not found, cannot run operator')
                return {'CANCELLED'}

        elif self.mode == 'STOP':
            State.playing = False
            return {'FINISHED'}

        else:
            self.report({'WARNING'}, 'invalid mode:'+self.mode)
            return {'FINISHED'}


    def clean(self, context):
        if self._handle_draw is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_draw, 'WINDOW')
            self._handle_draw = None
            State.playing = False

        if self._on_frame_change in bpy.app.handlers.frame_change_pre:
            bpy.app.handlers.frame_change_pre.append(self._on_frame_change)
            self._on_frame_change = None

        for tex in State.glplay_texs:
            tex.free()

        State.glplay_objs = []
        State.glplay_texs = []
        State.do_clean = None

class GLPlay_CreatePlayerDialog(bpy.types.Operator):
    bl_idname = "view3d.glplay_createpl_dialog"
    bl_label = "GL Play Create Player"
    bl_options = {'REGISTER', 'UNDO'}

    use_align_to_view = bpy.props.BoolProperty(default=True)

    dialog_width = 250

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label('choose image sequence:')
        col.prop(context.scene, 'glplay_selected_image', text='')
        col.prop(self, 'use_align_to_view', text='Align to View')

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_props_dialog(self, self.dialog_width)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        State.playing = False ## #temp

        img = context.scene.glplay_selected_image
        if img is None:
            self.report({'ERROR'}, "image not set")
            return {'CANCELLED'}

        tex = GLTexture(img, context.scene.frame_current) ## <!> to get size correctly
        w,h = img.size[:]
        m = max(w,h)
        tex.free()
        if m==0:
            self.report({'ERROR'}, "zero image size")
            return {'CANCELLED'}

        obj = create_mesh_obj(context.scene, w/m,h/m) if Pref.use_normalized_size  \
                                                      else create_mesh_obj(context.scene, w,h)
        if Pref.use_centering_origin:
            dp = obj.data.vertices[2].co *.5 *(-1)
            for v in obj.data.vertices:
                v.co += dp

        obj.glplay_image = img

        for so in context.selected_objects:
            so.select = False
        obj.select = True
        context.scene.objects.active = obj
        obj.location = context.scene.cursor_location

        if self.use_align_to_view:
            rv3d = context.space_data.region_3d
            obj.matrix_world = rv3d.view_matrix.inverted()
            obj.location = context.scene.cursor_location

        return {'FINISHED'}



class GLPlay_Panel(bpy.types.Panel):
    bl_label = "GLPlay Image Sequence"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        if State.playing:
            op = layout.operator(GLPlay_Operator.bl_idname, text='Stop', icon='PAUSE')
            op.mode = 'STOP'
        else:
            op = layout.operator(GLPlay_Operator.bl_idname, text='Start', icon='PLAY')
            op.mode = 'PLAY'

        col_misc = layout.column(align=True)
        active = not State.playing
        col_misc.active = active

        col_misc.separator()
        col_misc.operator(GLPlay_CreatePlayerDialog.bl_idname, text='Create Player')

        if context.object:
            col_misc2 = layout.column(align=True)
            col_misc2.separator()
            col = col_misc2.column(align=True)
            col.label('Active Object Image:')
            row = col.row()
            row.active = active
            row.prop(context.object, 'glplay_image', text='')
            col.prop(context.object, 'glplay_image_offset_frame', text='Frame Offset')
            col.prop(context.object, 'glplay_blendmode', text='Blend Mode')



@bpy.app.handlers.persistent
def on_load_pre(x):
    if State.do_clean:
        State.do_clean()
    State.playing = False

@bpy.app.handlers.persistent
def on_render_pre(scene):
    if State.do_clean:
        State.do_clean()
    State.playing = False


def register():
    def _tex_on_playing(self, context, f):
        if not State.playing:
            return
        for obj,tex in zip(State.glplay_objs, State.glplay_texs):
            if obj.name == self.name:
                f(self, context, obj, tex)
                return

    def prop_update_object(self, context):
        def f(self, context, obj, tex):
            tex.frame_offset = self.glplay_image_offset_frame
            tex.blendmode = self.glplay_blendmode
            tex.reload(context.scene.frame_current)
        _tex_on_playing(self, context, f)

    def tautology_to_enumitems(t):
        def str_to_enumid(s):
            s = s.upper()
            if len(s) == 0:
                return 0
            k=64
            head = ord(s[0])+k
            if len(s) == 1:
                return head
            tail = ord(s[-1])+k
            middle = sum([ord(c)+k for c in s[1:-1]])
            return int('{}{}{}'.format(head, middle, tail)) % 0xffffff ## <!> `0xffffff` for EnumProperty issue
        items = tuple([(n,n,'',str_to_enumid(n)) for n in sorted(t.__dict__)])
        ##
        check={}
        for n,_,_,enumid in items:
            if enumid in check:
                raise Exception('tautology_to_enumitems Error: detect enum-id duplication: {} / {}'.format(n,enumid))
            check[enumid] = True
        return items

    blends = tautology_to_enumitems(BlendMode)

    bpy.types.Object.glplay_image = bpy.props.PointerProperty(type=bpy.types.Image)
    bpy.types.Object.glplay_image_offset_frame = bpy.props.IntProperty(default=0, update=prop_update_object)
    bpy.types.Object.glplay_blendmode = bpy.props.EnumProperty(items=blends, default=BlendMode.ALPHAOVER, update=prop_update_object)
    bpy.types.Scene.glplay_selected_image = bpy.props.PointerProperty(type=bpy.types.Image)

    bpy.utils.register_class(GLPlay_Operator)
    bpy.utils.register_class(GLPlay_CreatePlayerDialog)
    bpy.utils.register_class(GLPlay_Panel)

    bpy.app.handlers.load_pre.append(on_load_pre)
    bpy.app.handlers.render_pre.append(on_render_pre)

def unregister():
    del bpy.types.Object.glplay_image
    del bpy.types.Object.glplay_image_offset_frame
    del bpy.types.Object.glplay_blendmode
    del bpy.types.Scene.glplay_selected_image
    bpy.utils.unregister_class(GLPlay_Panel)
    bpy.utils.unregister_class(GLPlay_CreatePlayerDialog)
    bpy.utils.unregister_class(GLPlay_Operator)

    bpy.app.handlers.load_pre.remove(on_load_pre)
    bpy.app.handlers.render_pre.remove(on_render_pre)


if __name__ == "__main__":
    register()
