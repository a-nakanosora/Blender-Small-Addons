'''
Blender Addon # AniMask

description:
    usage:
        1. start modal by View3D -> Tools -> AniMask -> "Start" button
        2. begin animation by [Alt+A]
        3. [Ctrl + MouseL Drag] while animation to draw
        4. exit by "Stop" button

    buttons:
        - "Animask Start"
        - "Stop" (key shortcut: [Esc])
        - "Clear" (key shortcut: [C])
            -- clear recorded locations

        - "New AMSet"

        - "Save To Curve"
            -- save active amset to active curve object
        - "Load From Curve"
            -- load amsets from selected curve objects
'''



bl_info = {
    "name": "AniMask",
    "description": "",
    "warning": "WIP",
    "author": "nk",
    "version": (0, 0, 1),
    "blender": (2, 7, 9),
    "location": "3D View > Tools > AniMask",
    "category": '3D View'
    }


import bpy
import bgl
import bpy_extras

from collections import namedtuple
from mathutils import Vector



Pref = None
State = None

def init():
    global Pref
    global State

    class _Pref:
        use_billboard = True
        #use_billboard = False

        default_blendmode = AMBlendMode.AlphaOver

        default_dissolve_method = AMDissolveMethod.OpacitySize

        default_dissolve_length = 50

        default_curve_name = 'animaskcurve'
        default_curvedata_name = 'animaskcurve'

        #use_scale_size_by_view_distance = False
        use_scale_size_by_view_distance = True
    Pref = _Pref

    class _State:
        frame = -1
        ready_to_record_loc = False
        current_ampointseq = None
        data = AMData()
        current_viewvec = None
        current_space = None
        running = False
        first_distance = 1.0
        brush_size = 20.0
        active_amset = None
    State = _State



def tautology(s):
    class _TautologyDict:
        def __setattr__(*args):
            raise Exception('tautology dict has only getters')
    dic = _TautologyDict()
    for n in s.strip().split():
        dic.__dict__[n] = n
    return dic

AMOpMode = tautology('''
    run
    stop
    clear
    load_data_from_curve
    save_data_to_curve
    new_amset
    _test
''')

AMBlendMode = tautology('''
    AlphaOver
    Additive
''')

AMDissolveMethod = tautology('''
    Opacity
    Size
    OpacitySize
    Const
''')

class VObject:pass



##
class AMData:
    def __init__(self):
        self.amsets = []

class AniMaskSet:
    def __init__(self):
        self.blendmode = Pref.default_blendmode
        self.dissolve_method = Pref.default_dissolve_method
        self.dissolve_length = Pref.default_dissolve_length
        self.image_texture = None
        self.reference_curve_name = ''
        self._ampseqs = []

    def add(self, ampseq):
        assert type(ampseq) is AniMaskPointSequence
        self._ampseqs.append(ampseq)
    def clear(self):
        self._ampseqs = []

    def get_ampseqs(self):
        return self._ampseqs.copy()
    #def replace_with(self, ampseqs):
    #    self._ampseqs = ampseqs

AniMaskPoint = namedtuple('AniMaskPoint', 'location, size, viewvec, frame')

class AniMaskPointSequence:
    def __init__(self):
        self._table = {}

    def set(self, frame, location=Vector(), size=1.0, viewvec=Vector()):
        self._table[frame] = AniMaskPoint(location, size, viewvec, frame)
    def get(self, frame):
        if frame in self._table:
            return self._table[frame]
        else:
            return None
    def clear(self):
        self._table = {}
    def all_points(self):
        return list(self._table.values())


def clear_sequences():
    for amset in State.data.amsets:
        for aseq in amset.get_ampseqs():
            aseq.clear()
    State.data.amsets = []


"""
<Data Structure Correspondence>
    curve <-> amset
    curve.splines[].points[] <-> amset._ampseqs[].amp[]

    ---

    curve.animask_texture_image  <->  amset.image_texture
    curve.animask_blendmode  <->  amset.blendmode
    curve.animask_dissolve_method  <->  amset.dissolve_method
    curve.animask_dissolve_length  <->  amset.dissolve_length

    ---

    point in curve.splines[].points, amp in amset.ampseqs[].all_points():
        point.co.x/y/z  <->  amp.location -- <!> point.co has 4 dimensions
        point.weight  <->  amp.frame -- first frame of the sequence
        point.radius  <->  amp.size
        //~~.handle_left/right  <->  amp.viewvec
"""

def data_from_curve(context, curveobj):
    assert Pref.use_billboard, 'now only supported on `Pref.use_billboard==True`'
    assert curveobj.type == 'CURVE'
    assert all([sp.type=='POLY' for sp in curveobj.data.splines])
    amset = AniMaskSet()
    amset.image_texture = curveobj.animask_texture_image
    amset.blendmode = curveobj.animask_blendmode
    amset.dissolve_method = curveobj.animask_dissolve_method
    amset.dissolve_length = curveobj.animask_dissolve_length
    amset.reference_curve_name = curveobj.name

    m = curveobj.matrix_world
    for sp in curveobj.data.splines:
        aseq = AniMaskPointSequence()
        #frame_first = round(sp.points[0].weight)
        frame_first = int(sp.points[0].weight)
        for i,spoint in enumerate(sp.points):
            #frame = spoint.weight
            frame = frame_first+i ## <!> frames depends on first point's weight
            location = Vector(spoint.co[0:3])
            size = spoint.radius
            viewvec = Vector() ## #todo
            aseq.set(frame, m*location, size, viewvec)
        amset.add(aseq)

    return amset


def data_to_curve(context, amset, curveobj=None):
    curvedata = bpy.data.curves.new(name=Pref.default_curvedata_name,type='CURVE')
    curvedata.dimensions = '3D'
    curvedata.show_handles = False
    curve = curveobj if curveobj is not None  \
                     else bpy.data.objects.new(Pref.default_curve_name, curvedata)
    curve.data = curvedata
    scene = context.scene
    if curve.name not in scene.objects:
        scene.objects.link(curve)

    curve.animask_texture_image = amset.image_texture
    curve.animask_blendmode = amset.blendmode
    curve.animask_dissolve_method = amset.dissolve_method
    curve.animask_dissolve_length = amset.dissolve_length

    m = curveobj.matrix_world.inverted()
    for aseq in amset.get_ampseqs():
        ps = aseq.all_points()
        ## #todo - sort ps by p.frame
        spline = curvedata.splines.new('POLY')
        spline.points.add(len(ps)-1) ## <!> '-1'

        for i,amp in enumerate(ps):
            assert type(amp) is AniMaskPoint
            spoint = spline.points[i]
            spoint.weight = amp.frame
            spoint.radius = amp.size
            loc = m*amp.location
            spoint.co.x = loc.x
            spoint.co.y = loc.y
            spoint.co.z = loc.z

    return curve






##
'''
def view_distance(context):
    return context.space_data.region_3d.view_distance
def view_location(context):
    return context.space_data.region_3d.view_location
'''

def region_2d_to_view_3d(context, pos2d, depth_location=None):
    region = context.region
    rv3d = context.space_data.region_3d
    vec3d = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, rv3d, pos2d)
    if depth_location is None:
        vec, viewpoint = get_viewpoint_coordinate(context)
        depth_location = viewpoint + vec

    loc3d = bpy_extras.view3d_utils.region_2d_to_location_3d(region, rv3d, pos2d, depth_location)
    return vec3d, loc3d


def view_3d_to_region_2d(context, co, local_to_global=False):
    area = context.area
    if area.type != 'VIEW_3D':
        raise Exception('view_3d_to_region_2d Error: invalid context.')
    viewport = area.regions[4]

    if local_to_global:
        co_3d = context.edit_object.matrix_world * co
    else:
        co_3d = co
    co_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(viewport, area.spaces[0].region_3d, co)
    return co_2d

def get_viewpoint_coordinate(context):
    region = context.region
    rv3d = context.space_data.region_3d
    p2d = Vector((region.width/2, region.height/2))
    viewpoint = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, rv3d, p2d)
    center_vec = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, rv3d, p2d)
    return center_vec, viewpoint

def get_viewpoint_coordinate2(context):
    if context.space_data.region_3d:
        return get_viewpoint_coordinate(context)
    else:
        ## e.g. when screen space changed
        return None, None


def draw_callback_3d(self, context):
    def draw(ps, cs):
        for p,c in zip(ps,cs):
            bgl.glColor4f(*c)
            bgl.glVertex3f(*p)
        bgl.glColor4f(*cs[0])
        bgl.glVertex3f(*ps[0])

    #bgl.glPushAttrib(bgl.GL_ALL_ATTRIB_BITS) ## #debug - stack context
    try:
        frcurrent = context.scene.frame_current
        for amset in State.data.amsets:
            frprevlimit = amset.dissolve_length
            for fr in range(frcurrent-frprevlimit, frcurrent+1):
                for aseq in amset.get_ampseqs():
                    amp = aseq.get(fr)
                    if not amp:
                        continue
                    viewvec = State.current_viewvec if Pref.use_billboard else amp.viewvec
                    dfr = frcurrent-fr
                    tfr = 1.0-dfr/frprevlimit if frprevlimit!=0 else 1.0

                    ##
                    u0 = viewvec.cross(Vector((0,0,1))).normalized() if abs(viewvec.z)!=1.0 else Vector((1,0,0))
                    v0 = u0.cross(viewvec)
                    size = amp.size
                    u = u0*size
                    v = v0*size
                    z_offset = fr/1000
                    #z_offset = fr/100
                    #z_offset = -dfr/50
                    #z_offset = -dfr/1000
                    #q = amp.location
                    q = amp.location - viewvec*z_offset
                    alpha, quadscale = 1,1
                    if amset.dissolve_method == AMDissolveMethod.Opacity:
                        #alpha = tfr
                        alpha = tfr**2.0
                    elif amset.dissolve_method == AMDissolveMethod.Size:
                        quadscale = tfr**2.0
                    elif amset.dissolve_method == AMDissolveMethod.OpacitySize:
                        alpha = tfr**2.0
                        quadscale = tfr**2.0
                    elif amset.dissolve_method == AMDissolveMethod.Const:
                        pass

                    u *= quadscale
                    v *= quadscale

                    cs = [(1,1,1,alpha), (1,1,1,.0), (1,1,1,.0), (1,1,1,.0)]
                    bgl.glEnable(bgl.GL_BLEND)

                    bgl.glDepthMask(bgl.GL_FALSE)

                    if amset.blendmode==AMBlendMode.AlphaOver:
                        ## alpha over
                        bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE_MINUS_SRC_ALPHA)
                        #bgl.glBlendFunc(bgl.GL_ONE, bgl.GL_ONE)
                        bgl.glBlendEquation(bgl.GL_FUNC_ADD)
                    elif amset.blendmode==AMBlendMode.Additive:
                        ## additive
                        bgl.glBlendEquation(bgl.GL_FUNC_ADD)
                        bgl.glBlendFunc(bgl.GL_SRC_ALPHA, bgl.GL_ONE)
                    else:
                        print('<!> invalid blendmode: '+amset.blendmode)

                    if amset.image_texture and amset.image_texture.bindcode[0]:
                        amset.image_texture.gl_touch(0)
                        bgl.glEnable(bgl.GL_TEXTURE_2D)
                        bgl.glColor4f(1.0, 1.0, 1.0, alpha)
                        bgl.glBindTexture(bgl.GL_TEXTURE_2D, amset.image_texture.bindcode[0])
                        bgl.glBegin(bgl.GL_QUADS)
                        ps = [q-u-v,q+u-v,q+u+v,q-u+v]
                        bgl.glTexCoord2f(0.0, 0.0)
                        bgl.glVertex3f(*ps[0])
                        bgl.glTexCoord2f(1.0, 0.0)
                        bgl.glVertex3f(*ps[1])
                        bgl.glTexCoord2f(1.0, 1.0)
                        bgl.glVertex3f(*ps[2])
                        bgl.glTexCoord2f(0.0, 1.0)
                        bgl.glVertex3f(*ps[3])
                        bgl.glEnd()
                        bgl.glDisable(bgl.GL_TEXTURE_2D)
                    else:
                        bgl.glBegin(bgl.GL_POLYGON)
                        draw([q,q+u,q+u+v,q+v], cs)
                        draw([q,q-u,q-u+v,q+v], cs)
                        draw([q,q+u,q+u-v,q-v], cs)
                        draw([q,q-u,q-u-v,q-v], cs)
                        bgl.glEnd()
                    bgl.glDisable(bgl.GL_BLEND)
                    bgl.glDepthMask(bgl.GL_TRUE)


        # restore opengl defaults
        bgl.glLineWidth(1)
        bgl.glDisable(bgl.GL_BLEND)
        bgl.glColor4f(0.0, 0.0, 0.0, 1.0)
    except Exception as e:
        print('error in draw callback')
        print(e)
    #bgl.glPopAttrib() ## #debug - restore context

def get_draw_ref_position(context):
    return context.scene.cursor_location




##
class AniMask_MainOperator(bpy.types.Operator):
    bl_idname = "view3d.animask_op"
    bl_label = "Animask Operator"

    mode = bpy.props.StringProperty(default='')

    _ctrldown = False
    _on_frame_change = None
    _on_load_pre = None
    _running = False
    _timer = None

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def modal(self, context, event):
        #print(event.type, event.value)
        #print('event.pressure', event.pressure) ## pentablet pressure

        viewvec, viewpoint = get_viewpoint_coordinate2(State.current_space)
        if viewvec is None:
            #return {'PASS_THROUGH'}
            self.clean(context)
            return {'CANCELLED'}
        State.current_viewvec = viewvec

        if event.type == 'TIMER':
            self._ctrldown = event.ctrl

        #if event.type in {'RIGHTMOUSE', 'ESC'}:
        if event.type in {'ESC'} or not State.running:
            self.clean(context)
            return {'CANCELLED'}

        if event.type in {'C'}:
            clear_sequences()
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE':
            #print('leftmouse')
            #if event.value == 'PRESS':
            if event.value == 'PRESS' and self._ctrldown:
                State.ready_to_record_loc = True
                a = AniMaskPointSequence()
                State.active_amset.add(a)
                State.current_ampointseq = a
                return {'RUNNING_MODAL'} ## prevent default
            elif event.value == 'RELEASE':
                State.ready_to_record_loc = False
                State.current_ampointseq = None
                return {'RUNNING_MODAL'} ## prevent default

        if State.ready_to_record_loc and State.current_ampointseq  \
                                     and State.frame != context.scene.frame_current:
            State.frame = context.scene.frame_current
            coord = event.mouse_region_x, event.mouse_region_y
            ref_pos = get_draw_ref_position(context)
            vec, loc = region_2d_to_view_3d(context, coord, ref_pos)
            assert type(loc) is Vector
            pr = event.pressure
            size = pr*3
            if Pref.use_scale_size_by_view_distance:
                dist = viewvec.dot(ref_pos - viewpoint)
                size *= dist/State.first_distance*State.first_size
            State.current_ampointseq.set(State.frame, loc, size, viewvec)


        if context.area:
            context.area.tag_redraw()
        return {'PASS_THROUGH'}

    def execute(self, context):
        if self.mode == AMOpMode.run:
            if State.running:
                return {'CANCELLED'}


            if State.active_amset is None:
                ## #temp
                amset = AniMaskSet()
                State.data.amsets.append(amset)
                State.active_amset = amset

            cs = VObject()
            #cs.region = context.region
            #cs.space_data = context.space_data
            ctx = context.copy()
            cs.region = ctx['region']
            cs.space_data = ctx['space_data']
            State.current_space = cs

            def f(scene):
                ## <!> needed for `use_billboard` -- to always update `current_viewvec` on frame change
                v,_ = get_viewpoint_coordinate2(State.current_space)
                if v is not None:
                    State.current_viewvec = v
            self._on_frame_change = f
            bpy.app.handlers.frame_change_pre.append(self._on_frame_change)

            wm = context.window_manager
            args = (self, context)
            self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
            wm.modal_handler_add(self)

            if self._on_load_pre is not None and self._on_load_pre in bpy.app.handlers.load_pre:
                bpy.app.handlers.load_pre.remove(self._on_load_pre)
                self._on_load_pre = None
            def on_load_pre(*args):
                State.running = False
                self.clean(context)
            self._on_load_pre = on_load_pre
            bpy.app.handlers.load_pre.append(self._on_load_pre)

            for amset in State.data.amsets:
                if amset.image_texture:
                    amset.image_texture.gl_load(0, bgl.GL_NEAREST, bgl.GL_NEAREST)

            ##

            ref_pos = get_draw_ref_position(context)
            a = Vector((0, 0))
            b = Vector((State.brush_size, 0))
            '''a = view_3d_to_region_2d(context, ref_pos)
            b = a+Vector((State.brush_size, 0))'''
            _, loc_a = region_2d_to_view_3d(context, a, ref_pos)
            _, loc_b = region_2d_to_view_3d(context, b, ref_pos)
            State.first_size = (loc_a-loc_b).length
            viewvec, viewpoint = get_viewpoint_coordinate(context)
            State.first_distance = viewvec.dot(ref_pos - viewpoint)

            self._timer = wm.event_timer_add(0.03, context.window)
            State.running = True
            return {'RUNNING_MODAL'}

        elif self.mode == AMOpMode.stop:
            State.running = False

        elif self.mode == AMOpMode.clear:
            clear_sequences()

        elif self.mode == AMOpMode.save_data_to_curve:

            for amset in State.data.amsets:
                if amset.reference_curve_name and amset.reference_curve_name in bpy.data.objects:
                    curve = bpy.data.objects[amset.reference_curve_name]
                    data_to_curve(context, amset, curve)
                else:
                    curvename = Pref.default_curve_name
                    curvedata = bpy.data.curves.new(name=Pref.default_curvedata_name,type='CURVE')
                    curvedata.dimensions = '3D'
                    curvedata.show_handles = False
                    curve = bpy.data.objects.new(curvename, curvedata)
                    if curve.name not in context.scene.objects:
                        context.scene.objects.link(curve)
                    amset.reference_curve_name = curve.name
                    data_to_curve(context, amset, curve)


        elif self.mode == AMOpMode.load_data_from_curve:
            cs = [obj for obj in context.selected_objects if obj.type=='CURVE']
            if cs:
                State.data.amsets = []
                actobj = context.active_object
                for curve in [c for c in cs if c.name != (actobj.name if actobj else '')] + (
                               [actobj] if actobj and actobj.type=='CURVE' else []):
                    amset = data_from_curve(context, curve)
                    data_to_curve(context, amset, curve) ## #test - re-update the curve object
                    State.data.amsets.append(amset)
                State.active_amset = State.data.amsets[-1] ## #temp

        elif self.mode == AMOpMode.new_amset:
            State.active_amset = None

        else:
            self.report({'WARNING'}, 'invalid mode: "{}"'.format(self.mode))
        return {'FINISHED'}

    def clean(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self._timer = None

        bpy.app.handlers.frame_change_pre.remove(self._on_frame_change)
        self._on_frame_change = None
        State.running = False

        wm = context.window_manager
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')

        if self._on_load_pre is not None and self._on_load_pre in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.remove(self._on_load_pre)
        self._on_load_pre = None

        for amset in State.data.amsets:
            if amset.image_texture:
                amset.image_texture.gl_free()

        context.area.tag_redraw()

class AniMask_UtilOperator(bpy.types.Operator):
    bl_idname = "view3d.animask_util_op"
    bl_label = "Animask Utils Operator"

    mode = bpy.props.StringProperty(default='')
    ##
    in_black = bpy.props.BoolProperty(default=False)
    col_orig_dif = bpy.props.FloatVectorProperty(default=(0,0,0))
    col_orig_spe = bpy.props.FloatVectorProperty(default=(0,0,0))
    col_theme_grad = bpy.props.FloatVectorProperty(default=(0,0,0))
    col_theme_highgrad = bpy.props.FloatVectorProperty(default=(0,0,0))
    prev_viewport_shade = bpy.props.StringProperty(default='')
    prev_use_matcap = bpy.props.BoolProperty(default=False)
    prev_show_world = bpy.props.BoolProperty(default=False)
    prev_show_only_render = bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    def execute(self, context):
        if self.mode == 'GENERATE_IMAGE':
            w = 64
            #w = 128
            h = w
            imgname = 'animask image'
            if imgname in bpy.data.images:
                img = bpy.data.images[imgname]
                if img.size[:] != (w, h):
                    img.scale(w,h)
            else:
                img = bpy.data.images.new(imgname, w, h, alpha=True)
            pixels = [1.0]*(w*h*4)
            c = w//2
            for y in range(h):
                for x in range(w):
                    idx = (y*w+x)*4
                    #pixels[idx+3] = 1.0-abs(x-c)/c
                    d = ((x-c)**2+(y-c)**2)**.5
                    pixels[idx+3] = 1.0-d/c if d<c else 0
            img.pixels = pixels

        elif self.mode == 'TOGGLE_BLACK_VIEW':
            viewlights = context.user_preferences.system.solid_lights
            themev3d = context.user_preferences.themes[0].view_3d.space

            if self.in_black:
                viewlights[0].use = True
                viewlights[1].use = True
                viewlights[2].diffuse_color = self.col_orig_dif[:]
                viewlights[2].specular_color = self.col_orig_spe[:]
                themev3d.gradients.gradient = self.col_theme_grad[:]
                themev3d.gradients.high_gradient = self.col_theme_highgrad[:]

                context.space_data.show_world = self.prev_show_world
                context.space_data.use_matcap = self.prev_use_matcap
                context.space_data.viewport_shade = self.prev_viewport_shade
                context.space_data.show_only_render = self.prev_show_only_render

                self.in_black = False
            else:
                self.col_orig_dif = viewlights[2].diffuse_color.copy()
                self.col_orig_spe = viewlights[2].specular_color.copy()
                self.col_theme_grad = themev3d.gradients.gradient.copy()
                self.col_theme_highgrad = themev3d.gradients.high_gradient.copy()
                self.prev_show_world = context.space_data.show_world
                self.prev_use_matcap = context.space_data.use_matcap
                self.prev_viewport_shade = context.space_data.viewport_shade
                self.prev_show_only_render = context.space_data.show_only_render

                viewlights[0].use = False
                viewlights[1].use = False
                viewlights[2].diffuse_color = (0,0,0)
                viewlights[2].specular_color = (0,0,0)
                themev3d.gradients.gradient = (0,0,0)
                themev3d.gradients.high_gradient = (0,0,0)

                context.space_data.show_world = False
                context.space_data.use_matcap = False
                context.space_data.viewport_shade = 'SOLID'
                context.space_data.show_only_render = True

                self.in_black = True

        return {'FINISHED'}

class AniMask_Panel(bpy.types.Panel):
    bl_label = "AniMask"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "Tools"
    bl_idname = 'view3d.animask_panel'
    bl_context = 'objectmode'



    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        row = col.row(align=True)
        op = row.operator(AniMask_MainOperator.bl_idname, text='Start')
        op.mode = AMOpMode.run
        row.active = not State.running

        row2 = col.row(align=True)
        op = row2.operator(AniMask_MainOperator.bl_idname, text='Stop')
        op.mode = AMOpMode.stop
        row2.active = State.running

        if State.running:
            layout.separator()
            col = layout.column(align=True)
            op = col.operator(AniMask_MainOperator.bl_idname, text='Clear')
            op.mode = AMOpMode.clear

        layout.separator()
        col = layout.column(align=True)
        col.label('amsets: {}'.format(len(State.data.amsets)))
        col.label('active amset: {}'.format(State.active_amset.reference_curve_name if State.active_amset else ''))
        if not State.running:
            op = col.operator(AniMask_MainOperator.bl_idname, text='New AMSet')
            op.mode = AMOpMode.new_amset

        layout.separator()
        col = layout.column(align=True)
        op = col.operator(AniMask_MainOperator.bl_idname, text='Save To Curve')
        op.mode = AMOpMode.save_data_to_curve
        op = col.operator(AniMask_MainOperator.bl_idname, text='Load From Curve')
        op.mode = AMOpMode.load_data_from_curve


        layout.separator()
        col = layout.column(align=True)
        obj = context.object
        if obj and obj.type=='CURVE':
            col.label('Image Texture:')
            col.prop(obj, 'animask_texture_image', text="")
            col.prop(obj, 'animask_blendmode', text="Blend Mode")
            col.prop(obj, 'animask_dissolve_method', text="Dissolve Method")
            col.prop(obj, 'animask_dissolve_length', text="Dissolve Length")

        layout.separator()
        col = layout.column(align=True)
        col.label('utils:')
        op = col.operator(AniMask_UtilOperator.bl_idname, text='Generate Image')
        op.mode = 'GENERATE_IMAGE'
        op = col.operator(AniMask_UtilOperator.bl_idname, text='Toggle Black View')
        op.mode = 'TOGGLE_BLACK_VIEW'





##
def register():
    init()

    def tautology_to_enumitems(t):
        return tuple([(n,n,'') for n in sorted(t.__dict__)])

    def prop_updated(self, context):
        if context.object.type != 'CURVE':
            return
        curve = context.object
        n = curve.name
        ams = ([ams for ams in State.data.amsets if ams.reference_curve_name == n]+[None])[0]
        if ams:
            State.data.amsets.remove(ams)
            ams2 = data_from_curve(context, curve)
            State.data.amsets.append(ams2)
            if State.active_amset is ams:
                State.active_amset = ams2

    def prop_updated_image(self, context):
        if '_animask_texture_image_prev' in self:
            if self['_animask_texture_image_prev'] is not None:
                self['_animask_texture_image_prev'].gl_free()
        if self.animask_texture_image is not None:
            self.animask_texture_image.gl_load(0, bgl.GL_NEAREST, bgl.GL_NEAREST)
        self['_animask_texture_image_prev'] = self.animask_texture_image
        prop_updated(self, context)


    bpy.types.Object.animask_texture_image = bpy.props.PointerProperty(type=bpy.types.Image, update=prop_updated_image)
    bpy.types.Object.animask_blendmode = bpy.props.EnumProperty(items=tautology_to_enumitems(AMBlendMode), default=Pref.default_blendmode, update=prop_updated)
    bpy.types.Object.animask_dissolve_method = bpy.props.EnumProperty(items=tautology_to_enumitems(AMDissolveMethod), default=Pref.default_dissolve_method, update=prop_updated)
    bpy.types.Object.animask_dissolve_length = bpy.props.IntProperty(default=Pref.default_dissolve_length, min=0, update=prop_updated)

    bpy.utils.register_class(AniMask_MainOperator)
    bpy.utils.register_class(AniMask_UtilOperator)
    bpy.utils.register_class(AniMask_Panel)


def unregister():
    bpy.utils.unregister_class(AniMask_MainOperator)
    bpy.utils.unregister_class(AniMask_UtilOperator)
    bpy.utils.unregister_class(AniMask_Panel)







if __name__ == "__main__":
    register()


