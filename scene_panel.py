import os
import shutil
import bpy
from bpy import ops
from bpy.props import *
from bpy.types import PropertyGroup

import bpy_extras

import bgl
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from mathutils import Matrix
from math import degrees

from bpy_extras.io_utils import (
        orientation_helper,
        axis_conversion,
        )

import json
import subprocess
import copy
import uuid

from threading import Timer, active_count

collision_types = {
    "shatter_collision_triangle" : "triangle",
    "shatter_collision_aabb" : "aabb",
    "shatter_collision_plane" : "plane",
    "shatter_collision_sphere" : "sphere"
}

light_types = {
    "POINT" : "0",
    "SUN" : "2",
    "SPOT" : "1",
    "AREA" : "3"
}

def GetTexture(obj):
    try:
        if len(obj.material_slots) > 0:
                tree = obj.material_slots[0].material.node_tree
                principled = None

                for node in tree.nodes:
                    if node.type == "BSDF_PRINCIPLED":
                        principled = node
                        break
              
                if principled != None:
                    filepath = ""

                    # Check if an image node is assigned to the Base Color input.
                    try:
                        # filepath = principled.inputs[0].links[0].from_node.image.filepath
                        base_color_index = principled.inputs.find("Base Color")
                        current_node_socket = principled.inputs[base_color_index]
                        for i in range(0,5):
                            current_node = current_node_socket.links[0].from_node
                            if(hasattr(current_node, 'image')):
                                filepath = current_node.image.filepath
                                print(filepath)
                                break;

                            current_node_socket = current_node.inputs[0]

                    # If not, check if it is the Shatter Default material configuration.
                    except Exception as e:
                        print("uh oh: " + str(e))
                        multiply_node1 = principled.inputs[0].links[0].from_node.inputs[1]
                        multiply_node2 = multiply_node1.links[0].from_node
                        image_node = multiply_node2.inputs[1].links[0].from_node
                        filepath = image_node.image.filepath

                    if len(filepath) == 0:
                        return None
                    
                    filepath = bpy.path.abspath(filepath)
                    split_name = os.path.splitext(os.path.basename(filepath))
                    system_name = split_name[0]
                    name = system_name.lower()
                    extension = split_name[1].lower()
                    
                    return {
                        "name" : name,
                        "extension" : extension,
                        "system_name" : system_name,
                        "path" : filepath
                    }
    except:
        pass

    return None

def ExportTexture(context, texture, asset):
    if len(texture['path']) == 0:
        print("Texture path not set. (" + texture["name"] + ")")
        return
    try:
        input_path = texture['path']
        output_path = bpy.path.abspath(context.scene.shatter_game_path + asset["path"])
        output_dir = os.path.dirname(output_path)
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)

        shutil.copy(input_path, output_path)
    except Exception as e:
        print("Failed to export texture. (" + str(e) + ")");

def GetRelativePath(value):
    try:
        game_path = bpy.path.abspath(bpy.context.scene.shatter_game_path)

        # Get the path relative to the game path.
        value = bpy.path.relpath(bpy.path.abspath(value), start=game_path)
    except:
        print("Invalid path \"" + value + "\".")

    # Remove the extra slashes at the start.
    value = value.lstrip('/')

    # Replace the backslashes with forward slashes if needed.
    value = value.replace('\\','/')

    return value

class KeyValueItem(PropertyGroup):
    value : StringProperty( name="Value", description="Value of the entry", default="")

class SLSS_UL_KeyValueList(bpy.types.UIList):
    bl_label = "Shatter Key Value List"
    bl_idname = "OBJECT_UL_ShatterKeyValueList"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            split = layout.split(factor=0.5)
            split.prop(item, "name", text="", emboss=False)
            split.prop(item, "value", text="", emboss=False)

        elif self.layout_type in {'GRID'}:
            pass

class ShatterKeyAdd(bpy.types.Operator):
    bl_idname = "object.shatter_key_add"
    bl_label = "Add Key Value"
    bl_description = "Adds key value to be exported with the object."

    def execute(self,context):
        obj = context.object

        obj.shatter_key_values.add()
        obj.shatter_key_value_index = len(obj.shatter_key_values) - 1

        obj.shatter_key_values[obj.shatter_key_value_index].name = "new_key"
        obj.shatter_key_values[obj.shatter_key_value_index].value = "new_value"

        return {'FINISHED'}

class ShatterKeyRemove(bpy.types.Operator):
    bl_idname = "object.shatter_key_remove"
    bl_label = "Remove Key Value"
    bl_description = "Removes key value to be exported with the object."

    def execute(self,context):
        obj = context.object

        index = obj.shatter_key_value_index

        obj.shatter_key_values.remove(index)
        obj.shatter_key_value_index = min(max(0, index - 1), len(obj.shatter_key_values) - 1)

        return {'FINISHED'}

class SLS_PT_ShatterObjectProperties(bpy.types.Panel):
    bl_label = "Additional Properties"
    bl_idname = "OBJECT_PT_ShatterObjectProperties"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_parent_id = "OBJECT_PT_ShatterObject"

    def draw(self, context):
        layout= self.layout
        obj = context.object

        row = layout.row()
        row.template_list("OBJECT_UL_ShatterKeyValueList", "Shatter Object Keys", obj, "shatter_key_values", obj, "shatter_key_value_index")

        col = row.column(align=True)
        col.operator("object.shatter_key_add", icon='ADD', text="")
        col.operator("object.shatter_key_remove", icon='REMOVE', text="")
        #col.separator()

        if len(obj.shatter_key_values) > 0:
            kv = obj.shatter_key_values[obj.shatter_key_value_index]
            if kv:
                row = layout.row()
                row.prop(kv, "value", text=kv.name)

def DrawText2D(color,position, text):
    font_id = 0
    blf.position(font_id, position[0], position[1], 0)
    blf.color(font_id, 0.0, 0.0, 0.0, 0.75)
    blf.size(font_id, 20)
    blf.draw(font_id, text)

    blf.position(font_id, position[0] - 1.0 , position[1] + 1.0, 0)
    blf.color(font_id, color[0], color[1], color[2], color[3])
    blf.size(font_id, 20)
    blf.draw(font_id, text)

def DrawText(color, position, text, offset=(0,0)):
    region = bpy.context.region
    region_3d = bpy.context.space_data.region_3d
    position2D = bpy_extras.view3d_utils.location_3d_to_region_2d(region, region_3d, position)

    position2D[0] += offset[0]
    position2D[1] += offset[1]

    DrawText2D(color,position2D,text)

def DrawLine(color, start, end):
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {"pos": [start,end]})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

def DrawLinkRaw(obj, prop, location, color):
    if obj.shatter_type not in bpy.context.scene.shatter_definitions:
        return
    
    for param in bpy.context.scene.shatter_definitions[obj.shatter_type]:
        if param["type"] == prop.type and param["key"] == prop.name:
            if "debug_color" in param:
                DrawLine(param["debug_color"], obj.location, location)
            else:
                DrawLine(color, obj.location, location)

def DrawLinkEntity(obj, prop, entity):
    if entity != None:
        DrawLinkRaw(obj,prop,entity.location, (0.0,0.6,0.3, 1.0))

def DrawLinkVector(obj, prop, vector):
    if vector != None:
        DrawLinkRaw(obj,prop,vector, (0.1,0.0,0.5, 1.0))

def DrawEntityLinkForObject(obj):
    for prop in obj.shatter_properties:
        if prop.type == "entities":
            for entity in prop.value_c:
                DrawLinkEntity(obj, prop, entity.value)
        elif prop.type == "entity":
            DrawLinkEntity(obj,prop,prop.value_o)
        elif prop.type == "vector":
            DrawLinkVector(obj,prop,prop.value_v)

def DrawEntityTextForObject(obj):
    color = (0.7,0.7,0.7, 1.0)
    scene = bpy.context.scene

    draw_label = True
    offset = [0,0]
    for prop in obj.shatter_properties:
        if prop.type == "entities":
            for entity in prop.value_c:
                if hasattr(entity.value, "location") == False:
                    continue

                if draw_label:
                    DrawText(color, entity.value.location, prop.name, tuple(offset))
                    draw_label = False
                    offset[0] += 10
                    offset[1] -= 20
                
                if entity.value != None:
                    if obj.shatter_type not in bpy.context.scene.shatter_definitions:
                        continue

                    for param in scene.shatter_definitions[obj.shatter_type]:
                        if param["type"] == prop.type and param["key"] == prop.name:
                            if "debug_color" in param:
                                text = entity.name + " execute " + entity.extra + "()"
                                if len(entity.extra) == 0:
                                    text = entity.value.name

                                DrawText(param["debug_color"], entity.value.location, text, tuple(offset))
                            else:
                                DrawText(color, entity.value.location, entity.name + " execute " + entity.extra + "()", tuple(offset))
                            offset[1] -= 20
                    draw_label = True
                    offset = [0,0]
        elif prop.type == "entity":
            entity = prop.value_o

            if hasattr(entity, "location") == False:
                continue

            if draw_label:
                DrawText(color, entity.location, prop.name, tuple(offset))
                draw_label = False
                offset[0] += 10
                offset[1] -= 20
            
            if entity != None:
                text = entity.name

                if obj.shatter_type not in bpy.context.scene.shatter_definitions:
                    continue

                for param in scene.shatter_definitions[obj.shatter_type]:
                    if param["type"] == prop.type and param["key"] == prop.name:
                        if "debug_color" in param:
                            DrawText(param["debug_color"], entity.location, text, tuple(offset))
                        else:
                            DrawText(color, entity.location, text, tuple(offset))
                        offset[1] -= 20
                draw_label = True
                offset = [0,0]


# This function goes through all objects that have link properties and draws the links.
def DrawEntityLinks():
    objects = bpy.context.selected_objects
    if bpy.context.scene.shatter_links_drawall == True:
        objects = bpy.context.visible_objects

    if len(objects) > 0:
        for obj in objects:
            DrawEntityLinkForObject(obj)
        return

    #for obj in bpy.context.scene.objects:
    #    DrawEntityLinkForObject(obj)

def DrawEntityTexts():
    if len(bpy.context.selected_objects) > 0:
        for obj in bpy.context.selected_objects:
            DrawEntityTextForObject(obj)
        return

    #for obj in bpy.context.scene.objects:
    #    DrawEntityTextForObject(obj)

def LinkToObject(target, link, clear=False):
    for prop in target.shatter_properties:
            if prop.name == "links" and prop.type == "entities":
                if clear:
                    prop.value_c.clear()

                for item in prop.value_c:
                    if item.value == link:
                        print("Already linked.")
                        return

                with bpy.context.temp_override(item=prop):
                    bpy.ops.object.shatter_object_add()
                    item = prop.value_c[len(prop.value_c) - 1]
                    item.value = link

def ClearLinksForObject(target):
    for prop in target.shatter_properties:
            if prop.name == "links" and prop.type == "entities":
                prop.value_c.clear()

def CheckAutomaticLinks(previous_object, active_object):
    if active_object == None or previous_object == None:
        return

    if active_object.name != previous_object.name:
        LinkToObject(previous_object, active_object)
        LinkToObject(active_object, previous_object)
        print( "Linking " + active_object.name + " to " + previous_object.name )

class ShatterObjectLink(bpy.types.Operator):
    bl_idname = "object.shatter_object_link"
    bl_label = "Link multiple Shatter nodes together"
    bl_options = {"GRAB_CURSOR"}

    def execute(self,context):
        objects = context.selected_objects

        if len(objects) == 1:
            ClearLinksForObject(objects[0])
            return {'FINISHED'}

        previous_object = None
        for current_object in context.selected_objects:
            CheckAutomaticLinks(previous_object, current_object)
            previous_object = current_object

        return {'FINISHED'}

class ObjectValueItem(PropertyGroup):
    value : PointerProperty(type=bpy.types.Object)
    extra : StringProperty(name="Input")

class ShatterObjectDuplicate(bpy.types.Operator):
    bl_idname = "object.shatter_object_duplicate"
    bl_label = "Duplicate last Object in List"

    def execute(self,context):
        obj = context.item

        size = len(obj.value_c)
        if size > 0 and obj.value_c[size - 1].value == None:
            return {'FINISHED'}

        latest = obj.value_c[size - 1]

        obj.value_c.add()
        obj.value_c_index = len(obj.value_c) - 1

        obj.value_c[obj.value_c_index].name = latest.name
        obj.value_c[obj.value_c_index].value = latest.value
        obj.value_c[obj.value_c_index].extra = latest.extra

        return {'FINISHED'}

class ShatterObjectAdd(bpy.types.Operator):
    bl_idname = "object.shatter_object_add"
    bl_label = "Add Object to List"

    def execute(self,context):
        obj = context.item

        size = len(obj.value_c)
        if size > 0 and obj.value_c[size - 1].value == None:
            return {'FINISHED'}


        obj.value_c.add()
        obj.value_c_index = len(obj.value_c) - 1

        obj.value_c[obj.value_c_index].name = ""
        obj.value_c[obj.value_c_index].value = None
        obj.value_c[obj.value_c_index].extra = ""

        return {'FINISHED'}

class ShatterObjectRemove(bpy.types.Operator):
    bl_idname = "object.shatter_object_remove"
    bl_label = "Remove Object from List"

    def execute(self,context):
        obj = context.item

        index = obj.value_c_index

        obj.value_c.remove(index)
        obj.value_c_index = min(max(0, index - 1), len(obj.value_c) - 1)

        return {'FINISHED'}

class SLSS_UL_ObjectList(bpy.types.UIList):
    bl_label = "Shatter Object List"
    bl_idname = "OBJECT_UL_ShatterObjectList"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row()
            display_name = active_data.name == "outputs"
            if not display_name:
                row.separator()
            row.prop_search(item, "value", bpy.context.scene, "objects", text="")
            row = layout.row()

            if display_name:
                row.prop(item, "name", text="")
                row.prop(item, "extra", text="")

        elif self.layout_type in {'GRID'}:
            pass

def GetFilePath(self):
    if "value_file" in self:
        return self["value_file"]
    
    return ""

def SetFilePath(self, value):
    value = GetRelativePath(value)
    self["value_file"] = value

class BoundsProperty(bpy.types.PropertyGroup):
    minimum: FloatVectorProperty()
    maximum: FloatVectorProperty()

class DefinitionType(bpy.types.PropertyGroup):
    type: StringProperty( default="string")
    subtype : StringProperty()

    value_s: StringProperty()
    value_file: StringProperty(subtype="FILE_PATH", get=GetFilePath, set=SetFilePath)
    value_f: FloatProperty()
    value_i: IntProperty()
    value_b: BoolProperty()
    value_v: FloatVectorProperty()
    value_o: PointerProperty(type=bpy.types.Object)
    value_c: CollectionProperty(type=ObjectValueItem)
    value_c_index: IntProperty(default=0)
    value_bd: PointerProperty(type=BoundsProperty)
    value_falloff: EnumProperty(
        items=(
            ("inversesqr", "Inverse Square", ""),
            ("linear", "Linear", ""),
            ("none", "None", "")
        ),
        name="Falloff Type",
        description="Determines how the volume of a sound is modulated based on its distance to the listener."
        )
    value_bus: EnumProperty(
        items=(
            ("0", "SFX", ""),
            ("1", "Dialogue", ""),
            ("2", "Music", ""),
            ("3", "UI", ""),
            ("4", "Auxilery3", ""),
            ("5", "Auxilery4", ""),
            ("6", "Auxilery5", ""),
            ("7", "Auxilery6", ""),
            ("8", "Auxilery7", ""),
            ("9", "Auxilery8", ""),
            ("10", "Master", "")
        ),
        name="Bus Type",
        description="Determines which sound bus will be picked for a sound."
        )

def GetPropertyValue(obj, prop):
    if prop.type == "string":
        if prop.subtype == "file":
            return prop.value_file
        return prop.value_s
    elif prop.type == "float":
        return str(prop.value_f)
    elif prop.type == "vector" or prop.type == "color":
        return VectorToString(prop.value_v)
    elif prop.type == "int":
        return str(prop.value_i)
    elif prop.type == "bool":
        if prop.value_b is True:
            return "1"
        else:
            return "0"
    elif prop.type == "entity":
        if prop.value_o:
            return str(prop.value_o.name)
        else:
            return ""
    elif prop.type == "entities" and len(prop.value_c) > 0:
        result = []
        if prop.name == "outputs":
            for item in prop.value_c:
                if item.value == None:
                    continue

                result.append({"name" : item.name, "target" : item.value.name,"input" : item.extra})
            return result
        else:
            for item in prop.value_c:
                if item.value == None:
                    continue

                result.append(item.value.name)
            return result
    elif prop.type == "bounds":
        return VectorToString(prop.value_bd.minimum) + "," + VectorToString(prop.value_bd.maximum)
    elif prop.type == "auto_bounds":
        if(obj.type != "EMPTY"):
            maximum = obj.dimensions * 0.5
        else:
            maximum = obj.empty_display_size * obj.scale

        minimum = -maximum
        return VectorToString(minimum) + "," + VectorToString(maximum)
    elif prop.type == "auto_float":
        if(obj.type != "EMPTY"):
            value = min(obj.dimensions) * 0.5
        else:
            value = obj.empty_display_size * min(obj.scale)
        
        return str(value)
    elif prop.type == "falloff":
        return str(prop.value_falloff)
    elif prop.type == "bus":
        return str(prop.value_bus)
    else:
        return None

ValidDisplayTypes = [
        "string",
        "float",
        "vector",
        "color",
        "int",
        "bool",
        "entity",
        "entities",
        "bounds",
        "falloff",
        "bus"
    ]

def DisplayProperty(layout, kv):
    if kv.type not in ValidDisplayTypes:
        return

    row = layout.row()
    split = row.split(factor=0.25)
    
    split.label(text=kv.name)

    if kv.type == "string":
        if kv.subtype == "file":
            split.prop(kv, "value_file", text="")
        else:
            split.prop(kv, "value_s", text="")
    elif kv.type == "float":
        split.prop(kv, "value_f", text="")
    elif kv.type == "vector" or kv.type == "color":
        split.prop(kv, "value_v", text="")
    elif kv.type == "int":
        split.prop(kv, "value_i", text="")
    elif kv.type == "bool":
        split.prop(kv, "value_b", text="")
    elif kv.type == "entity":
        split.prop_search(kv, "value_o", bpy.context.scene, "objects", text="")
    elif kv.type == "entities":
        split.template_list("OBJECT_UL_ShatterObjectList", "Shatter Object List", kv, "value_c", kv, "value_c_index")
        col = row.column(align=True)
        col.context_pointer_set("item", kv)
        col.operator("object.shatter_object_add", icon='ADD', text="")
        col.operator("object.shatter_object_remove", icon='REMOVE', text="")
        col.operator("object.shatter_object_duplicate", icon='DUPLICATE', text="")
    elif kv.type == "bounds":
        split.prop(kv.value_bd, "minimum", text="")
        split.prop(kv.value_bd, "maximum", text="")
    elif kv.type == "falloff":
        split.prop(kv, "value_falloff", text="")
    elif kv.type == "bus":
        split.prop(kv, "value_bus", text="")
    else:
        split.label(text="(read-only)")



def GetLightType(type):
    if type == "light":
        return "OUTLINER_OB_LIGHT"
    elif type == "sound":
        return "PLAY_SOUND"

    return "PROP_PROJECTED"

class SLS_PT_ShatterObject(bpy.types.Panel):
    bl_label = "Shatter Object"
    bl_idname = "OBJECT_PT_ShatterObject"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout

        obj = context.object

        row = layout.row()
        row.prop(obj, "shatter_export")

        if obj.shatter_export == False:
            return

        row.prop(obj, "shatter_visible")

        row = layout.row()
        row.prop(obj, "name")

        if obj.instance_type == "COLLECTION":
            row = layout.row()
            row.label(text=str(obj.instance_collection.library.filepath))
            row = layout.row()
            row.prop(obj, "shatter_prefab")
            return

        row = layout.row()

        icontype = GetLightType(obj.shatter_type)

        row.prop_search(obj, "shatter_type", bpy.context.scene, "shatter_object_types", text="Type", icon=icontype)
        # row.prop(obj, "shatter_type")
        if obj.shatter_type in bpy.context.scene.shatter_object_types:
            description = [bpy.context.scene.shatter_object_types[obj.shatter_type].value]

            if obj.shatter_type in bpy.context.scene.shatter_definitions:
                output_line = ""
                for entry in bpy.context.scene.shatter_definitions[obj.shatter_type]:
                    first_entry = len(output_line) == 0
                    if entry['type'] == "input":
                        if not first_entry:
                            output_line += ", "
                        output_line += str(entry['key'])
                if len(output_line) > 0:
                    output_line = "Inputs: " + output_line
                    description.append(output_line)

                output_line = ""
                for entry in bpy.context.scene.shatter_definitions[obj.shatter_type]:
                    first_entry = len(output_line) == 0
                    if entry['type'] == "output":
                        if not first_entry:
                            output_line += ", "
                        output_line += str(entry['key'])
                if len(output_line) > 0:
                    output_line = "Outputs: " + output_line
                    description.append(output_line)

            for line in description:
                # Ignore if we aren't actually displaying any information.
                if len(description) == 1 and len(line) == 0:
                    continue

                row = layout.row()
                row.label(text=line)

        if obj.shatter_type == "custom":
            row = layout.row()
            row = row.prop(obj, "shatter_type_custom")

        if obj.shatter_type != "custom" and obj.type != "EMPTY" and obj.type != "LIGHT":
            row = layout.row()
            row.prop(obj, "shatter_collision")

            if obj.shatter_collision:
                row = layout.row()
                row.prop(obj, "shatter_collision_type")
                row = layout.row()
                row.prop(obj, "shatter_collision_mobility")
                row = layout.row()
                row.prop(obj, "shatter_collision_damping")
                row = layout.row()
                row.prop(obj, "shatter_collision_friction")
                row = layout.row()
                row.prop(obj, "shatter_collision_restitution")
                row = layout.row()
                row.prop(obj, "shatter_collision_drag")
        
            row = layout.row()
            row.prop(obj, "shatter_shader_type")

            if obj.shatter_shader_type == "custom":
                row = layout.row()
                row.prop(obj, "shatter_shader_type_custom")

        if obj.shatter_type == "mesh":
            row = layout.row()
            row.prop(obj, "shatter_animation")
            row = layout.row()
            row.prop(obj, "shatter_animation_playrate")
            row = layout.row()
            row.prop(obj, "shatter_maximum_render_distance")

            if len(obj.material_slots) > 0:
                row = layout.row()
                row.prop(obj.material_slots[0].material, "shatter_material")

from io_scene_fbx import export_fbx_bin

def VectorToString(vector):
    return str(format(vector[0],'f')) + ' ' + str(format(vector[1],'f')) + ' ' + str(format(vector[2],'f'))

def Vector4ToString(vector):
    return str(format(vector[0],'f')) + ' ' + str(format(vector[1],'f')) + ' ' + str(format(vector[2],'f')) + ' ' + str(format(vector[3],'f'))

axis_forward = "-Z"
axis_up = "Y"

generated_meshes = []
generated_textures = []
def ResetExporter():
    generated_meshes.clear()
    generated_textures.clear()

def GetBasePath(context):
    game_path = os.path.normpath(bpy.path.abspath(context.scene.shatter_game_path))
    export_path = os.path.normpath(bpy.path.abspath(context.scene.shatter_export_path + "\\..\\"))

    return export_path + "/"

def GetBasePathRelative(context):
    game_path = os.path.normpath(bpy.path.abspath(context.scene.shatter_game_path))
    export_path = os.path.normpath(bpy.path.abspath(context.scene.shatter_export_path))

    relative_path = bpy.path.relpath(export_path, start=game_path)

    # Remove the extra slashes at the start.
    relative_path = relative_path.lstrip('/')

    # Replace the backslashes with forward slashes if needed.
    relative_path = relative_path.replace('\\','/')

    return relative_path + "/"

def GetModPathAbsolute(context):
    return os.path.normpath(bpy.path.abspath(context.scene.shatter_game_path + GetBasePathRelative(context)))


def ExportData(operator, context, export_path, whole_scene = False, animation_only = False, **keywords):
    if whole_scene or animation_only:
        export_fbx_bin.save(operator, context, export_path, False, False, "SCENE", True, **keywords)
    else:
        depsgraph = context.evaluated_depsgraph_get()
        export_fbx_bin.save_single(operator, context.scene, depsgraph, export_path, **keywords)

@orientation_helper(axis_forward='-Z', axis_up='Y')
def ExportAnimations(operator,context):
    global_matrix = (axis_conversion(to_forward=axis_forward,
                                         to_up=axis_up,
                                         ).to_4x4())

    # Set global matrix to identity to prevent modifier application issues.
    # global_matrix = Matrix()

    keywords = {
    #    'use_selection': False, 
    #    'use_active_collection': False, 
        'global_scale': 1.0, 
        'apply_unit_scale': True,  # Make sure to apply the unit scale
        'apply_scale_options': 'FBX_SCALE_ALL', # Scale all needed for Shatter
        'bake_space_transform': False, 
        'object_types': {'ARMATURE', 'CAMERA'}, # Used to also export EMPTY but that isn't really ideal right now.
        'use_mesh_modifiers': True, 
        'use_mesh_modifiers_render': True, 
        'mesh_smooth_type': 'OFF', 
        'use_subsurf': False, 
        'use_mesh_edges': False, 
        'use_tspace': False,  # Export tangent space vectors
        'use_custom_props': False, 
        'add_leaf_bones': True, 
        'primary_bone_axis': 'Y', 
        'secondary_bone_axis': 'X', 
        'use_armature_deform_only': False, 
        'armature_nodetype': 'NULL', 
        'bake_anim': True, 
        'bake_anim_use_all_bones': True, 
        'bake_anim_use_nla_strips': True, 
        'bake_anim_use_all_actions': False, 
        'bake_anim_force_startend_keying': True, 
        'bake_anim_step': 1.0, 
        'bake_anim_simplify_factor': 1.0, 
        'path_mode': 'AUTO', 
        'embed_textures': False, 
    #    'batch_mode': 'SCENE', 
    #    'use_batch_own_dir': True, 
        'use_metadata': True, 
        'axis_forward': '-Z', 
        'axis_up': 'Y',
        "global_matrix" : global_matrix
    }

    try:
        export_dir = os.path.normpath(bpy.path.abspath(GetBasePath(context)))
        export_path = export_dir + "/Models/"

        if not os.path.isdir(export_dir):
            print("Creating directory: " + export_dir)
            try:
                os.mkdir(export_dir)
            except e:
                print("Error: " + str(e))

        print("Exporting animations to: " + export_path)

        ExportData(operator,context,export_path,False,True, **keywords)
    except Exception as e:
        print("ExportAnimations failed: " + str(e) + ".")

    bpy.context.view_layer.update()

@orientation_helper(axis_forward='-Z', axis_up='Y')
def GenerateAsset(operator,context,exported,obj, armature = None):
    if obj.type == "MESH":
        asset_name = obj.data.name.lower()
        
        if asset_name in generated_meshes:
            return

        animation_only = context.scene.shatter_animation_only == True

        if animation_only:
            asset_name += "anim"

        if animation_only and armature is None:
            return

        asset = {}
        asset["type"] = "mesh"
        asset["name"] = asset_name
        asset["path"] = GetBasePathRelative(context) + "Models/" + asset_name + ".fbx"
        exported["assets"].append(asset)
        generated_meshes.append(asset_name)

        texture = GetTexture(obj)
        if texture != None and texture['name'] not in generated_textures and animation_only != True:
            texture_asset = {}
            texture_asset["type"] = "texture"
            texture_asset["name"] = texture['name']
            texture_asset["path"] = "Textures/" + texture['system_name'] + texture['extension']
            exported["assets"].append(texture_asset)
            generated_textures.append(texture['name'])

            if context.scene.shatter_export_textures == True:
                ExportTexture(context, texture, texture_asset)

        if context.scene.shatter_export_meshes == False and animation_only == False:
            return

        global_matrix = (axis_conversion(to_forward=axis_forward,
                                         to_up=axis_up,
                                         ).to_4x4())

        # Set global matrix to identity to prevent modifier application issues.
        # global_matrix = Matrix()

        keywords = {
            'use_selection': True, 
            'use_active_collection': False, 
            'global_scale': 1.0, 
            'apply_unit_scale': True,  # Make sure to apply the unit scale
            'apply_scale_options': 'FBX_SCALE_ALL', # Scale all needed for Shatter
            'bake_space_transform': False, 
            'object_types': {'OTHER', 'MESH', 'ARMATURE', 'EMPTY', 'LIGHT', 'CAMERA'}, 
            'use_mesh_modifiers': True, 
            'use_mesh_modifiers_render': True, 
            'mesh_smooth_type': 'OFF', 
            'use_subsurf': False, 
            'use_mesh_edges': False, 
            'use_tspace': True,  # Export tangent space vectors
            'use_custom_props': False, 
            'add_leaf_bones': True, 
            'primary_bone_axis': 'Y', 
            'secondary_bone_axis': 'X', 
            'use_armature_deform_only': False, 
            'armature_nodetype': 'NULL', 
            'bake_anim': True, 
            'bake_anim_use_all_bones': True, 
            'bake_anim_use_nla_strips': True, 
            'bake_anim_use_all_actions': True, 
            'bake_anim_force_startend_keying': True, 
            'bake_anim_step': 1.0, 
            'bake_anim_simplify_factor': 1.0, 
            'path_mode': 'AUTO', 
            'embed_textures': False, 
            'batch_mode': 'OFF', 
            'use_batch_own_dir': True, 
            'use_metadata': True, 
            'axis_forward': '-Z', 
            'axis_up': 'Y',
            "global_matrix" : global_matrix
        }

        original_matrix = copy.deepcopy(obj.matrix_world)
        obj.matrix_world = Matrix()

        if animation_only == False:
            keywords["context_objects"] = [obj]
        else:
            keywords["context_objects"] = []
            keywords["bake_anim"] = True
            keywords["bake_anim_use_all_bones"] = True
            keywords["bake_anim_use_nla_strips"] = True
            keywords["bake_anim_use_all_actions"] = False
            keywords["bake_anim_force_startend_keying"] = True
            keywords["bake_anim_step"] = 1.0
            keywords["bake_anim_simplify_factor"] = 1.0
            keywords["batch_mode"] = "SCENE"

        if armature != None:
            keywords["context_objects"].append(armature)

        try:
            export_dir = os.path.normpath(bpy.path.abspath(context.scene.shatter_game_path))
            export_path = export_dir + "/" + asset["path"]
            models_dir = os.path.dirname(export_path)

            print("Export directory: " + export_dir)
            print("Export path: " + export_path)
            print("Model directory: " + models_dir)

            if not os.path.isdir(models_dir):
                print("Creating directory: " + models_dir)
                try:
                    os.mkdir(models_dir)
                except Exception as e:
                    print("Error: " + str(e))

            ExportData(operator,context,export_path, False, animation_only, **keywords)
        except Exception as e:
            print("GenerateAsset failed: " + str(e) + ".")
        
        obj.matrix_world = original_matrix
        bpy.context.view_layer.update()

def GetShader(obj, texture = None):
    if( obj.shatter_shader_type == "custom"):
        return obj.shatter_shader_type_custom

    if texture != None:
        return "DefaultTextured"
    
    return "DefaultGrid"

def ParseNode(obj, entity):
    if obj.type != "MESH":
        return
    
    deps = bpy.context.evaluated_depsgraph_get()
    eval = obj.evaluated_get(deps)

    nodes = ""
    for vertex in eval.data.vertices:
        position = obj.matrix_world @ vertex.co
        nodes += str(vertex.index) + "," + VectorToString(position) + ";"
    
    connections = ""
    for edge in eval.data.edges:
        connections += str(edge.vertices[0]) + "," + str(edge.vertices[1]) + ";"

    entity["nodes"] = nodes
    entity["edges"] = connections

    return

def ParseObject(operator,context,exported, obj, recurse = True, parent = None):
    if obj.shatter_export == False:
        return

    for collection in obj.users_collection:
        if collection.name in context.view_layer.layer_collection.children:
            view_collection = context.view_layer.layer_collection.children[collection.name]
            if view_collection.hide_viewport == True or collection.hide_render == True:
                return

    armature = None
    if obj.type == "MESH" and obj.parent != None and obj.parent.type == "ARMATURE":
        armature = obj.parent

    if obj.shatter_type != "node": # Don't generate assets for nodes. (their mesh is stored directly in the level file for now)
        GenerateAsset(operator,context,exported,obj, armature)

    shatter_name = obj.get("shatter_name", obj.name)

    if obj.type == "LIGHT":
        obj.shatter_type = "light"
    
    if obj.type == "EMPTY":
        if obj.instance_type == "COLLECTION" and recurse:
            # print("Collection: " + obj.name + " (" + str(len(obj.instance_collection.objects)) + ")")

            if len(obj.shatter_prefab) > 0:
                # print("Prefab path: " + obj.shatter_prefab)
                obj.shatter_type = "level"
            else:
                for child in obj.instance_collection.objects:
                    ParseObject(operator,context,exported,child, False, obj)
                return
            # print("End of Collection: " + obj.name)
        else:
            print("Unknown empty type. (" + obj.name + ")")
            if "Limestone" in obj.name:
                print("Lime")


    if len(obj.shatter_type) > 0:
        # print("Shatter Type: " + obj.shatter_type)
        entity = {}

        name_prefix = ""
        if parent and parent.shatter_type == "level":
            name_prefix = parent.get("shatter_name", parent.name)

        # Generate the unique identifier.
        if len(obj.shatter_uuid) == 0:
                obj.shatter_uuid = str( uuid.uuid4() )

        if obj.shatter_type != "level":
            entity["name"] = name_prefix + shatter_name
            entity["uuid"] = obj.shatter_uuid

        if obj.shatter_type != "custom":
            entity["type"] = obj.shatter_type
        else:
            if len(obj.shatter_type_custom) > 0:
                entity["type"] =  obj.shatter_type_custom
            else:
                entity["type"] = "mesh"

        is_level = entity["type"] == "level"
        if is_level and len(obj.shatter_prefab) == 0:
            return

        if is_level:
            # print("Prefab sub-level " + obj.shatter_prefab)
            entity["path"] = obj.shatter_prefab + ".sls"
            
            # Handle level UUIDs.
            entity["uuid"] = obj.shatter_uuid #"00000000-0000-0000-0000-000000000000"

        undefined_type = entity["type"] not in context.scene.shatter_definitions

        should_export_transform = True
        if undefined_type == False:
            definition = context.scene.shatter_definitions[entity["type"]]
            for param in definition:
                if param["key"] == "no_transform":
                    should_export_transform = False

        # Fetch the mesh name if we're a mesh object.
        mesh_type = False
        light_type = False
        if (not undefined_type or entity["type"] == "mesh") and obj.type == "MESH":
            # print("Mesh " + obj.data.name)
            entity["mesh"] = obj.data.name.lower()
            mesh_type = True
        elif undefined_type and obj.type == "LIGHT" and obj.data.type != "SUN":
            mesh_type = False
            light_type = True
        elif not is_level and undefined_type:
            # Type likely isn't supported. Skip.
            print("Unsupported type " + entity["type"])
            return
        
        if obj.shatter_type == "node" or obj.shatter_type == "rope":
            ParseNode(obj,entity)

        HasMaterial = False
        if not is_level and mesh_type and len(obj.material_slots) > 0:
            if obj.material_slots[0].material is not None and len(obj.material_slots[0].material.shatter_material) > 0:
                entity["material"] = str(obj.material_slots[0].material.shatter_material)
                HasMaterial = True

        if not HasMaterial and not is_level and mesh_type:
            entity["shader"] = "DefaultGrid"

            texture = GetTexture(obj)
            if texture != None:
                entity["texture"] = texture['name']
                entity["shader"] = "DefaultTextured"
            else:
                entity["texture"] = "error"

            entity["shader"] = GetShader(obj,texture)

        original_matrix = copy.deepcopy(obj.matrix_world)
        original_color = obj.color
        if parent != None:
            obj.matrix_world = parent.matrix_world @ obj.matrix_world
            obj.color[0] = parent.color[0]
            obj.color[1] = parent.color[1]
            obj.color[2] = parent.color[2]
            obj.color[3] = parent.color[3]
        
        if obj.parent:
            entity["parent"] = obj.parent.name;

        if should_export_transform:
            position = copy.deepcopy(obj.location)
            
            entity["position"] = VectorToString(position)
            # entity["position"] = "0 0 0"

            rotation = copy.deepcopy(obj.rotation_euler)

            rotation.x = degrees(obj.rotation_euler.y)
            rotation.y = degrees(obj.rotation_euler.x)
            rotation.z = degrees(obj.rotation_euler.z)

            entity["rotation"] = VectorToString(rotation)
            # entity["rotation"] = "0 0 0"

            if not light_type:
                entity["scale"] = VectorToString(obj.scale)

        if not is_level and light_type and obj.data.type != "SUN":
            entity["light_type"] = light_types[obj.data.type]
            entity["radius"] = str(obj.data.shadow_soft_size * 6.28)
            entity["intensity"] = str(obj.data.energy * 3.14)
            entity["color"] = VectorToString(obj.data.color)

            if obj.data.type == "SPOT":
                entity["angle_inner"] = str(obj.data.spot_blend * obj.data.spot_size)
                entity["angle_outer"] = str(obj.data.spot_size)

        if not is_level and obj.shatter_type != "custom" and obj.type != "EMPTY" and not light_type:
            if obj.color[3] > 200.0:
                print("Light sphere value: " + Vector4ToString(obj.color))

            if obj.color[3] != 1.0:
                entity["color"] = Vector4ToString(obj.color)
            else:
                entity["color"] = VectorToString(obj.color)
            entity["visible"] = "1" if obj.shatter_visible else "0"
            entity["collision"] = "1" if obj.shatter_collision else "0"
            entity["collisiontype"] = collision_types[obj.shatter_collision_type]
            if obj.shatter_collision:
                if obj.shatter_collision_mobility == None:
                    entity["static"] = "1"
                    entity["stationary"] = "1"

                if obj.shatter_collision_mobility == "shatter_collision_static":
                    entity["static"] = "1"
                else:
                    entity["static"] = "0"

                if obj.shatter_collision_mobility == "shatter_collision_stationary":
                    entity["stationary"] = "1"
                else:
                    entity["stationary"] = "0"

                if obj.shatter_collision_mobility == "shatter_collision_dynamic":
                    entity["static"] = "0"
                    entity["stationary"] = "0"

            entity["damping"] = str(obj.shatter_collision_damping)
            entity["friction"] = str(obj.shatter_collision_friction)
            entity["restitution"] = str(obj.shatter_collision_restitution)
            entity["drag"] = str(obj.shatter_collision_drag)

        if mesh_type and len(obj.shatter_animation) > 0:
            entity["animation"] = obj.shatter_animation
            entity["playrate"] = str(obj.shatter_animation_playrate)

        if mesh_type and obj.shatter_maximum_render_distance > 0.0:
            entity["maximum_render_distance"] = str(obj.shatter_maximum_render_distance)
        
        additional_key_values = obj.shatter_key_values
        for pair in additional_key_values:
            entity[pair.name] = pair.value

        if parent:
            additional_key_values = parent.shatter_key_values

        for pair in additional_key_values:
            entity[pair.name] = pair.value

        for pair in obj.shatter_properties:
            value = GetPropertyValue(obj, pair)
            if value != None:
                entity[pair.name] = value

        exported["entities"].append(entity)

        obj.matrix_world = original_matrix
        obj.color = original_color

def ExportObjects(operator,context):
    objects = context.scene.objects

    ResetExporter()

    scene_id = str( uuid.uuid4() )
    if len(context.scene.shatter_uuid) > 0:
        scene_id = context.scene.shatter_uuid
    else:
        context.scene.shatter_uuid = scene_id

    exported = {
        "version" : "0",
        "uuid" : scene_id,
        "save" : "1" if context.scene.shatter_allow_serialization else "0",
        "assets" : [],
        "entities" : []
    }

    # Don't export the sky assets and add it to the script if we're exporting in Bare mode.
    if context.scene.shatter_is_bare == False:
        sky_shader_asset = {}
        sky_shader_asset["type"] = "shader"
        sky_shader_asset["name"] = "sky"
        sky_shader_asset["path"] = "Shaders/Sky"
        exported["assets"].append(sky_shader_asset)

        sky_night_asset = {}
        sky_night_asset["type"] = "texture"
        sky_night_asset["name"] = "sky"
        sky_night_asset["path"] = "Textures/MilkyWayPanorama.png"
        exported["assets"].append(sky_night_asset)

        sky = {}
        sky["name"] = "sky"
        sky["type"] = "sky"
        sky["mesh"] = "sky"
        sky["shader"] = "sky"
        sky["texture"] = "sky"
        sky["position"] = "0 0 0"
        sky["rotation"] = "0 0 0"
        sky["scale"] = "1900 1900 1900"
        sky["uuid"] = "00000000-0000-0000-0000-000000000001"
        exported["entities"].append(sky)

    default_shader = {}
    default_shader["type"] = "shader"
    default_shader["name"] = "DefaultGrid"
    default_shader["path"] = "Shaders/DefaultGrid"
    exported["assets"].append(default_shader)

    default_texture_shader = {}
    default_texture_shader["type"] = "shader"
    default_texture_shader["name"] = "DefaultTextured"
    default_texture_shader["path"] = "Shaders/DefaultTextured"
    exported["assets"].append(default_texture_shader)

    if context.scene.shatter_animation_only == False:
        obj_index = 0 # Used to update the progress indicator.
        for obj in objects:
            ParseObject(operator,context,exported,obj)

            # Update the progress indicator.
            obj_index += 1
            bpy.context.window_manager.progress_update((obj_index / len(objects)) * 0.97)

        print("Configured " + str(len(exported["assets"])) + " assets.")
        print("Configured " + str(len(exported["entities"])) + " entities.")
    else:
         ExportAnimations(operator,context)

    if context.scene.shatter_animation_only == True:
        return {}

    if context.scene.shatter_no_script == True:
        return {}

    return exported

class ExportScene(bpy.types.Operator):
    bl_idname = "shatter.export_scene"
    bl_label = "Export"
    bl_description = "Exports the current scene to a Shatter level file"

    def execute(self,context):
        bpy.context.window_manager.progress_begin(0, 100)

        exported = ExportObjects(self,context)

        if(len(exported) == 0):
            if context.scene.shatter_animation_only:
                self.report({"INFO"}, "Exported animation only.")
            else:
                self.report({"INFO"}, "Exported geometry only.")
            return {'FINISHED'}

        export_path = context.scene.shatter_export_path + context.scene.name + ".sls"
        full_path = bpy.path.abspath(export_path)
        self.report({"INFO"}, "Exporting level script to " + export_path)

        export_file = open(full_path, 'w')
        json.dump(exported, export_file, indent=4)

        bpy.context.window_manager.progress_end()

        return {'FINISHED'}

def camera_position(matrix):
    """ From 4x4 matrix, calculate camera location """
    t = (matrix[0][3], matrix[1][3], matrix[2][3])
    r = (
      (matrix[0][0], matrix[0][1], matrix[0][2]),
      (matrix[1][0], matrix[1][1], matrix[1][2]),
      (matrix[2][0], matrix[2][1], matrix[2][2])
    )
    rp = (
      (-r[0][0], -r[1][0], -r[2][0]),
      (-r[0][1], -r[1][1], -r[2][1]),
      (-r[0][2], -r[1][2], -r[2][2])
    )
    output = (
      rp[0][0] * t[0] + rp[0][1] * t[1] + rp[0][2] * t[2],
      rp[1][0] * t[0] + rp[1][1] * t[1] + rp[1][2] * t[2],
      rp[2][0] * t[0] + rp[2][1] * t[1] + rp[2][2] * t[2],
    )
    return output

class RunWorld(bpy.types.Operator):
    bl_idname = "shatter.run_world"
    bl_label = "Run"
    bl_description = "Launches the game and loads the world."

    def execute(self,context):
        if len( context.scene.shatter_game_path ) == 0 or len( context.scene.shatter_game_executable ) == 0:
            self.report({"WARNING"}, "No game path or executable specified.")
            return {'FINISHED'}
        
        full_path = bpy.path.abspath(context.scene.shatter_game_path + context.scene.shatter_game_executable + ".exe")
        working_directory = bpy.path.abspath(context.scene.shatter_game_path)

        # Fetch view space coordinates for camera placement.
        camera_location = (0,0,0)
        camera_direction = (0,0,0)
        for area in context.window.screen.areas:
            if area.type == "VIEW_3D":
                camera_location = camera_position(area.spaces[0].region_3d.view_matrix)
                camera_direction = area.spaces[0].region_3d.view_rotation.to_euler('XYZ')

        x = round(camera_location[0],3)
        y = round(camera_location[1],3)
        z = round(camera_location[2],3)
        print("Location x " + str(x) + " y " + str(y) + " z " + str(z))

        x = str(x)
        y = str(y)
        z = str(z)

        # Replace the minus sign with a plus.
        x = x.replace("-", "+")
        y = y.replace("-", "+")
        z = z.replace("-", "+")

        camera_direction.x = degrees(camera_direction.y)
        camera_direction.y = degrees(camera_direction.x)
        camera_direction.z = degrees(camera_direction.z)

        print("Direction " + str(camera_direction))

        dirx = round(camera_direction[0],3)
        diry = round(camera_direction[1],3)
        dirz = round(camera_direction[2],3)

        dirx = str(dirx)
        diry = str(diry)
        dirz = str(dirz)

        # Replace the minus sign with a plus.
        dirx = dirx.replace("-", "+")
        diry = diry.replace("-", "+")
        dirz = dirz.replace("-", "+")

        level_path = context.scene.shatter_export_path.removeprefix(context.scene.shatter_game_path)

        command_list = [
            full_path, 
            "-world",level_path + context.scene.name, 
            "-x", x, "-y", y, "-z", z,
            "-dirx", dirx, "-diry", diry, "-dirz", dirz
        ]

        if(context.scene.shatter_moveplayer == True):
            command_list.append("-moveplayer")

        subprocess.Popen(command_list, cwd=working_directory)

        return {'FINISHED'}

class ExportAndRunWorld(bpy.types.Operator):
    bl_idname = "shatter.export_scene_run_world"
    bl_label = "Export & Run"
    bl_description = "Exports the scene and then launches the game, loading the world."

    def execute(self,context):
        bpy.ops.shatter.export_scene()
        bpy.ops.shatter.run_world()

        return {'FINISHED'}

class SLS_PT_ShatterScene(bpy.types.Panel):
    bl_label = "Shatter Scene"
    bl_idname = "OBJECT_PT_ShatterScene"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        row = layout.row()
        row.prop(scene, "shatter_game_path")
        row = layout.row()
        row.prop(scene, "shatter_game_executable")
        row = layout.row()
        row.prop(scene, "shatter_export_path")

        row = layout.row()
        row.label(text="Options")
        row = layout.row()
        row.prop(scene, "shatter_export_meshes")
        #row = layout.row()
        row.prop(scene, "shatter_export_textures")

        row = layout.row()
        row.prop(scene, "shatter_is_bare")
        row.enabled = scene.shatter_no_script == False and scene.shatter_animation_only == False
        row.prop(scene, "shatter_allow_serialization")

        row = layout.row()
        row.prop(scene, "shatter_no_script")
        row.enabled = scene.shatter_animation_only == False

        row = layout.row()
        row.prop(scene, "shatter_animation_only")
        row.enabled = True

        # Additional startup options
        row = layout.row()
        col = row.column(align=True)
        opt = col.row()
        opt.label(text="Startup Options")

        opt = col.row()
        opt.prop(scene, "shatter_moveplayer")

        # Editor options
        col = row.column(align=True)
        opt = col.row()
        opt.label(text="Editor Options")

        opt = col.row()
        opt.prop(scene, "shatter_links_drawall")

        row = layout.row()
        row.operator("shatter.export_scene", icon="EXPORT")

        row = layout.row()
        row.operator("shatter.run_world", icon="TEXT")

        row = layout.row()
        row.operator("shatter.export_scene_run_world", icon="PLAY")

        json_only = scene.shatter_export_meshes == False and scene.shatter_export_textures == False
        if json_only:
            row = layout.row()
            row.label(text="Only the main scene will be exported. (JSON-only)")

class OutputType(bpy.types.PropertyGroup):
    target: PointerProperty(type=bpy.types.Object)
    input: StringProperty()

class SLSS_UL_DefinitionList(bpy.types.UIList):
    bl_label = "Shatter Definition List"
    bl_idname = "OBJECT_UL_ShatterDefinitionList"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.alignment = 'CENTER'
            layout.label(text=item.name)

        elif self.layout_type in {'GRID'}:
            pass

class SLS_PT_ShatterObjectDefinitions(bpy.types.Panel):
    bl_label = "Properties"
    bl_idname = "OBJECT_PT_ShatterObjectDefinitions"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_parent_id = "OBJECT_PT_ShatterObject"

    def draw(self, context):
        layout= self.layout
        obj = context.object

        for prop in obj.shatter_properties:
            DisplayProperty(layout, prop)

        if len(obj.shatter_properties) == 0:
            layout.label(text="This entity has no associated properties.")

def ApplyDefinition(obj, clear=True):
    if not hasattr(obj, "shatter_type"):
        return

    type = obj.shatter_type

    if type not in bpy.types.Scene.shatter_definitions:
        if clear == True:
            obj.shatter_properties.clear()
        return

    if clear == True:
        obj.shatter_properties.clear()

    definitions = bpy.types.Scene.shatter_definitions[type]

    # Check which definitions are missing.
    # Copy the existing property names.
    existing_names = [prop.name for prop in obj.shatter_properties]

    # Get all of the definitions that aren't already defined in the shatter_properties collection.
    missing_definitions = [definition for definition in definitions if definition["key"] not in existing_names]

    # If we're not clearing, make sure to purge orphaned properties.
    if clear == False:
        accounted_props = []
        for definition in definitions:
            for prop in obj.shatter_properties:
                if definition["key"] == prop.name and definition["type"] == prop.type:
                    accounted_props.append(prop.name)

        unaccounted_props = []
        for prop in obj.shatter_properties:
            if prop.name not in accounted_props:
                unaccounted_props.append(prop.name)

        for prop in unaccounted_props:
            index = obj.shatter_properties.find(prop)
            if index > -1:
                obj.shatter_properties.remove(index)

    for definition in missing_definitions:
        item = obj.shatter_properties.add()
        item.name = definition["key"]
        item.type = definition["type"]

        if "subtype" in definition:
            item.subtype = definition["subtype"]

def OnTypeUpdate(self,context):
    ApplyDefinition(self)

class LoadDefinitions(bpy.types.Operator):
    bl_idname = "shatter.load_definitions"
    bl_label = "Reload Definitions"
    bl_description = "Loads entity definitions if available."

    # These are protected key names that should not be overwritten.
    # Fields that use these names are ignored.
    filtered_keys = ["name", "help", "transform", "inputs", "outputs"]

    entity_types = []
    native_types = 0
    entity_meta = {} # Property information.

    def SeedTypes(self):
        self.entity_types = []
        self.entity_types.append(("mesh", "Mesh",""))
        self.entity_types.append(("level", "Level",""))
        self.entity_types.append(("custom", "Custom",""))
        self.entity_types.append(("light", "Light",""))
        self.native_types = len(self.entity_types)

    def ApplyTypes(self):
        self.entity_types = tuple(self.entity_types)

        if bpy.types.Scene.shatter_definitions:
            del bpy.types.Scene.shatter_definitions
        bpy.types.Scene.shatter_definitions = self.entity_meta

        additional_types = len(self.entity_types) - self.native_types
        print(str(additional_types) + " additional types found.")
        print(str(len(self.entity_meta)) + " meta types.")

    def Finish(self, context):
        self.ApplyTypes()
        
        # Add the entity types to the object types list
        bpy.context.scene.shatter_object_types.clear()
        for item in self.entity_types:
            sceneitem = bpy.context.scene.shatter_object_types.add()
            sceneitem.name = item[0]
            sceneitem.value = item[2]

        # Fix up some of the base types if they were corrupted
        for obj in context.scene.objects:
            if not hasattr(obj, "shatter_type"):
                continue
            
            type = obj.shatter_type
            if len(type) == 0:
                if obj.type == "LIGHT":
                    obj.shatter_type = "light"
                elif obj.type == "EMPTY":
                    obj.shatter_type = "logic_point"
                else:
                    obj.shatter_type = "mesh"

        self.ApplyDefinitions(context)

    def execute(self,context):
        definitions_path = bpy.path.abspath(context.scene.shatter_game_path + "Definitions.fgd")

        # Add the default Shatter types.
        self.SeedTypes()

        # Wipe existing property information.
        self.entity_meta.clear()

        # Add outputs to the default Shatter types.
        self.entity_meta["mesh"] = []
        self.entity_meta["mesh"].append({"key" : "outputs", "type" : "entities", "debug_color" : (0.6, 0.1, 0.0, 1.0)})

        if not os.path.isfile(definitions_path):
            print("No definitions file found. (" + definitions_path + ")")
            self.Finish(context)
            return {'FINISHED'}

        with open(definitions_path) as definition_file:
            print("Loading definitions. (" + definitions_path + ")")
            definitions = json.load(definition_file)
            if "types" in definitions:
                for item in definitions["types"]:
                    if "name" in item:
                        # Check if a description/help field was included.
                        description = item["help"] if "help" in item else ""

                        # Add the entity's name to the type array.
                        self.entity_types.append((item["name"],item["name"].capitalize(), description))

                        if item["name"] not in self.entity_meta:
                            self.entity_meta[item["name"]] = []

                        # Get all the additional properties.
                        for meta in item.items():
                            data = {}

                            key = meta[0]
                            type = meta[1]

                            if key in self.filtered_keys:
                                continue

                            data["key"] = key

                            type_info = type.split(',', 1)
                            data["type"] = type_info[0]

                            if len(type_info) > 1:
                                if data["type"] == "entities" or data["type"] == "entity":
                                    colors = type_info[1].lstrip('(').rstrip(')').split(',')
                                    colors = [float(c) for c in colors]

                                    if len(colors) == 3:
                                        colors.append(1.0)

                                    data["debug_color"] = tuple(colors)
                                elif data["type"] == "string":
                                    if type_info[1] == "dir":
                                        data["subtype"] = "dir"
                                    elif type_info[1] == "file":
                                        data["subtype"] = "file"

                            self.entity_meta[item["name"]].append(data)

                        # Add outputs field
                        if "outputs" in item:
                            if item["name"] not in self.entity_meta:
                                    self.entity_meta[item["name"]] = []
                        
                            # Output list
                            self.entity_meta[item["name"]].append({"key" : "outputs", "type" : "entities", "debug_color" : (0.6, 0.1, 0.0, 1.0)})

                            # Output meta-data
                            for output in item["outputs"]:
                                self.entity_meta[item["name"]].append({"key" : output, "type" : "output"})

                        if "inputs" in item:
                            if item["name"] not in self.entity_meta:
                                    self.entity_meta[item["name"]] = []

                            # Input meta-data
                            for input in item["inputs"]:
                                self.entity_meta[item["name"]].append({"key" : input, "type" : "input"})

                        if "transform" in item and item["transform"] == False:
                            if item["name"] not in self.entity_meta:
                                    self.entity_meta[item["name"]] = []
                        
                            self.entity_meta[item["name"]].append({"key" : "no_transform", "type" : "no_transform"})

        self.Finish(context)

        return {'FINISHED'} 

    def ApplyDefinitions(self, context):
        for obj in context.scene.objects:
                ApplyDefinition(obj, False)


@bpy.app.handlers.persistent
def InitializeDefinitions(parameters):
    bpy.ops.shatter.load_definitions()

def OnGamePathUpdate(self,context):
    print("Reloading definitions.")
    # Load the entity definitions.
    bpy.ops.shatter.load_definitions()

def GetDummyEntityList():
    entity_types = []

    entity_types.append(("mesh", "Mesh",""))
    entity_types.append(("level", "Level",""))
    entity_types.append(("custom", "Custom",""))
    entity_types.append(("light", "Light",""))

    #for i in range(0,1000):
    #    entity_types.append(("unknown", "Unknown descriptor",""))

    return tuple(entity_types)

# Getters are required if a setter exists.
def GetPrefab(self):
    if "shatter_prefab" in self:
        return self["shatter_prefab"]
        
    return ""

# Used to set the prefab path to its relative directory
def SetPrefab(self, value):
    if value.startswith("Levels/"):
        self["shatter_prefab"] = value

        # Strip the extension.
        value = value.rstrip(".sls")
        return
    
    value = GetRelativePath(value)

    # Strip the extension.
    value = value.rstrip(".sls")
    self["shatter_prefab"] = value

classes = (
    KeyValueItem,
    SLSS_UL_KeyValueList,

    ObjectValueItem,
    SLSS_UL_ObjectList,
    ShatterObjectLink,
    ShatterObjectDuplicate,
    ShatterObjectAdd,
    ShatterObjectRemove,
    BoundsProperty,
    DefinitionType,

    SLS_PT_ShatterScene,
    SLS_PT_ShatterObject,
    SLS_PT_ShatterObjectDefinitions,
    SLS_PT_ShatterObjectProperties,

    ExportScene,
    RunWorld,
    ExportAndRunWorld,
    LoadDefinitions,

    ShatterKeyAdd,
    ShatterKeyRemove
)

addon_keymap = []
def RegisterKeyConfig():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = wm.keyconfigs.addon.keymaps.new(name='3D View Generic', space_type='VIEW_3D')
        kmi = km.keymap_items.new(ShatterObjectLink.bl_idname, type='D', value='RELEASE', ctrl=True, alt=True)
        addon_keymap.append((km, kmi))
        print( "Added key mapping")

def UnregisterKeyConfig():
    for km, kmi in addon_keymap:
        km.keymap_items.remove(kmi)
    addon_keymap.clear()

def RegisterScenePanels():
    # Register all of the classes
    for cls in classes:
        bpy.utils.register_class(cls)

    RegisterKeyConfig()
    
    Scene = bpy.types.Scene

    # Register scene panel properties.
    Scene.shatter_export_path = StringProperty(name="Levels Path",description="Export location of the main level file", subtype="DIR_PATH")
    Scene.shatter_game_path = StringProperty(name="Game Path",description="Location of the game's executable", subtype="DIR_PATH", update=OnGamePathUpdate)
    Scene.shatter_game_executable = StringProperty(name="Game Executable",description="Name of the game's executable")
    Scene.shatter_export_meshes = BoolProperty(name="Meshes",description="Determines whether meshes should be exported",default=True)
    Scene.shatter_export_textures = BoolProperty(name="Textures",description="Determines whether textures should be exported",default=True)

    Scene.shatter_is_bare = BoolProperty(name="Bare",description="Bare files don't include things like the sky mesh by default",default=True)
    Scene.shatter_allow_serialization = BoolProperty(name="Serialization",description="Allows this level to write save files",default=True)
    Scene.shatter_no_script = BoolProperty(name="Geometry Only",description="Don't export any level script data",default=False)
    Scene.shatter_animation_only = BoolProperty(name="Animation Only",description="Export just animation data",default=False)

    Scene.shatter_uuid = StringProperty(name="UUID",description="Unique identifier for the Shatter engine.")

    Scene.shatter_definitions = []
    Scene.shatter_previous_object = None

    Scene.shatter_object_types = CollectionProperty(type = KeyValueItem)

    # Additional startup options
    Scene.shatter_moveplayer = BoolProperty(name="Move Player",description="Move the player to the viewport location",default=False)

    # Editor options
    Scene.shatter_links_drawall = BoolProperty(name="Always show links",description="Displays links for every object, when disabled it only shows links for selected objects",default=True)

    # Register object properties.
    Object = bpy.types.Object
    Object.shatter_collision = BoolProperty(name="Collision",description="Enables collisions for this object.",default=True)
    Object.shatter_collision_type = EnumProperty(
        items=(
            ("shatter_collision_triangle", "Triangle Mesh", "Use triangle mesh collision tests."),
            ("shatter_collision_aabb", "Bounding Box", "Use AABB collision tests."),
            ("shatter_collision_plane", "Planar", "Use plane collision tests."),
            ("shatter_collision_sphere", "Spherical", "Use spherical collision tests.")
        ),
        name="Collision Type",
        description="Determines how objects interact with this objects in the physics engine."
        )
    
    Object.shatter_collision_damping = FloatProperty(name="Damping", default=1.0)
    Object.shatter_collision_friction = FloatProperty(name="Friction", default=0.5)
    Object.shatter_collision_restitution = FloatProperty(name="Restitution", default=1.0)
    Object.shatter_collision_drag = FloatProperty(name="Drag", default=1.0)

    Object.shatter_collision_mobility = EnumProperty(
        items=(
            ("shatter_collision_static", "Static", "Static body"),
            ("shatter_collision_stationary", "Stationary", "Immovable object."),
            ("shatter_collision_dynamic", "Dynamic", "Simulated body")
        ),
        name="Mobility",
        description="Determines how the object's movement is handled."
        )

    Object.shatter_type = StringProperty(
        name="Entity",
        description="",
        update=OnTypeUpdate,
        default="mesh"
        )

    Object.shatter_type_custom = StringProperty(name="Type",description="Custom Shatter entity type")

    Object.shatter_shader_type = EnumProperty(
        items=(
            ("automatic", "Automatic", ""),
            ("DefaultTextured", "Textured", ""),
            ("DefaultGrid", "Grid", ""),
            ("custom", "Custom", "")
        ),
        name="Shader",
        description=""
        )

    Object.shatter_shader_type_custom = StringProperty(name="Type",description="Custom Shatter shader type")

    Object.shatter_animation = StringProperty(name="Animation",description="Animation that this mesh should play by default")
    Object.shatter_animation_playrate = FloatProperty(name="Play Rate",description="Animation play rate",default=1.0,min=0.0,soft_min=0.0,soft_max=10.0)

    Object.shatter_maximum_render_distance = FloatProperty(name="Maximum Render Distance",description="Distance from the camera at which the object should be culled, infinite when negative",default=-1.0,min=-1.0)

    Object.shatter_key_values = CollectionProperty(type = KeyValueItem)
    Object.shatter_key_value_index = IntProperty(name="Key Value Index", default=0)

    Object.shatter_properties = CollectionProperty(type = DefinitionType)

    Object.shatter_visible = BoolProperty(name="Visible",description="Should this object be visible in the engine?",default=True)
    Object.shatter_export = BoolProperty(name="Export",description="When disabled, this object is never exported",default=True)

    Object.shatter_prefab = StringProperty(name="Prefab",description="Where to look for the prefab if relevant", subtype="FILE_PATH", get=GetPrefab, set=SetPrefab)
    Object.shatter_uuid = StringProperty(name="UUID",description="Unique identifier for the Shatter engine")

    Material = bpy.types.Material
    Material.shatter_material = StringProperty(name="Material",description="Name that is used to refer to this material within the engine itself")

    Scene.DrawHandler = bpy.types.SpaceView3D.draw_handler_add(DrawEntityLinks, (), 'WINDOW', 'POST_VIEW')
    Scene.TextHandler = bpy.types.SpaceView3D.draw_handler_add(DrawEntityTexts, (), 'WINDOW', 'POST_PIXEL')

    bpy.app.handlers.load_post.append(InitializeDefinitions)

    # Use a timer to prod the operator, it's not possible to execute it straight away.
    # Timer(0.1, InitializeDefinitions, ["test"]).start()

def UnregisterScenePanels():
    # Unregister all of the classes
    for cls in classes:
        bpy.utils.unregister_class(cls)

    UnregisterKeyConfig()

    bpy.app.handlers.load_post.remove(InitializeDefinitions)

    Scene = bpy.types.Scene

    bpy.types.SpaceView3D.draw_handler_remove(Scene.DrawHandler, 'WINDOW')
    bpy.types.SpaceView3D.draw_handler_remove(Scene.TextHandler, 'WINDOW')

    # Unregister scene panel properties.
    del Scene.shatter_export_path
    del Scene.shatter_game_path
    del Scene.shatter_game_executable
    del Scene.shatter_export_meshes
    del Scene.shatter_export_textures

    del Scene.shatter_is_bare
    del Scene.shatter_allow_serialization
    del Scene.shatter_no_script
    del Scene.shatter_animation_only

    del Scene.shatter_uuid

    del Scene.shatter_definitions
    del Scene.shatter_previous_object
    del Scene.shatter_object_types

    del Scene.shatter_moveplayer
    del Scene.shatter_links_drawall

    Object = bpy.types.Object

    # Unregister object properties.
    del Object.shatter_collision
    del Object.shatter_collision_type
    del Object.shatter_collision_damping
    del Object.shatter_collision_friction
    del Object.shatter_collision_restitution
    del Object.shatter_collision_drag

    del Object.shatter_collision_mobility
    del Object.shatter_type
    del Object.shatter_type_custom

    del Object.shatter_shader_type
    del Object.shatter_shader_type_custom

    del Object.shatter_animation
    del Object.shatter_animation_playrate

    del Object.shatter_maximum_render_distance

    del Object.shatter_key_values
    del Object.shatter_key_value_index
    del Object.shatter_properties

    del Object.shatter_visible
    del Object.shatter_export

    del Object.shatter_prefab
    del Object.shatter_uuid

    Material = bpy.types.Material

    # Unregister material properties.
    del Material.shatter_material