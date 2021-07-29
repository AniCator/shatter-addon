import os
import shutil
import bpy
from bpy import ops
from bpy.props import *
from bpy.types import PropertyGroup

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

from threading import Timer

collision_types = {
    "shatter_collision_triangle" : "triangle",
    "shatter_collision_aabb" : "aabb",
    "shatter_collision_plane" : "plane"
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
                        filepath = principled.inputs[0].links[0].from_node.image.filepath

                    # If not, check if it is the Shatter Default material configuration.
                    except:
                        multiply_node1 = principled.inputs[0].links[0].from_node.inputs[1]
                        multiply_node2 = multiply_node1.links[0].from_node
                        image_node = multiply_node2.inputs[1].links[0].from_node
                        filepath = image_node.image.filepath
                    
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
    try:
        shutil.copy(texture['path'], bpy.path.abspath(context.scene.shatter_game_path + asset["path"]))
    except:
        print("Failed to export texture.")

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

class ObjectValueItem(PropertyGroup):
    value : PointerProperty(type=bpy.types.Object)

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
            layout.separator()
            layout.prop_search(item, "value", bpy.context.scene, "objects", text="")

        elif self.layout_type in {'GRID'}:
            pass

class DefinitionType(bpy.types.PropertyGroup):
    type: StringProperty( default="string")

    value_s: StringProperty()
    value_f: FloatProperty()
    value_i: IntProperty()
    value_b: BoolProperty()
    value_v: FloatVectorProperty()
    value_o: PointerProperty(type=bpy.types.Object)
    value_c: CollectionProperty(type=ObjectValueItem)
    value_c_index: IntProperty(default=0)

def GetPropertyValue(prop):
    if prop.type == "string":
        return prop.value_s
    elif prop.type == "float":
        return str(prop.value_f)
    elif prop.type == "vector":
        return VectorToString(prop.value_v)
    elif prop.type == "int":
        return str(prop.value_i)
    elif prop.type == "bool":
        if prop.value_b is True:
            return "1"
        else:
            return "0"
    elif prop.type == "entity":
        return str(prop.value_o.name)
    elif prop.type == "entities":
        result = []
        for item in prop.value_c:
            result.append(item.name)
        return str(result)

def DisplayProperty(layout, kv):
    row = layout.row()
    split = row.split(factor=0.25)
    
    split.label(text=kv.name)

    if kv.type == "string":
        split.prop(kv, "value_s", text="")
    elif kv.type == "float":
        split.prop(kv, "value_f", text="")
    elif kv.type == "vector":
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
        row.prop(obj, "shatter_type")

        if obj.shatter_type == "custom":
            row = layout.row()
            row = row.prop(obj, "shatter_type_custom")

        if obj.shatter_type != "custom" and obj.type != "EMPTY":
            row = layout.row()
            row.prop(obj, "shatter_collision")

            if obj.shatter_collision:
                row = layout.row()
                row.prop(obj, "shatter_collision_type")
        
            row = layout.row()
            row.prop(obj, "shatter_shader_type")

            if obj.shatter_shader_type == "custom":
                row = layout.row()
                row.prop(obj, "shatter_shader_type_custom")

from io_scene_fbx import export_fbx_bin

def VectorToString(vector):
    return str(format(vector[0],'f')) + ' ' + str(format(vector[1],'f')) + ' ' + str(format(vector[2],'f'))

axis_forward = "-Z"
axis_up = "Y"

generated_meshes = []
generated_textures = []
def ResetExporter():
    generated_meshes.clear()
    generated_textures.clear()

@orientation_helper(axis_forward='-Z', axis_up='Y')
def GenerateAsset(operator,context,exported,obj):
    if obj.type == "MESH":
        asset_name = obj.data.name.lower()
        if asset_name in generated_meshes:
            return

        asset = {}
        asset["type"] = "mesh"
        asset["name"] = asset_name
        asset["path"] = "Models/" + asset_name + ".fbx"
        exported["assets"].append(asset)
        generated_meshes.append(asset_name)

        texture = GetTexture(obj)
        if texture != None and texture['name'] not in generated_textures:
            texture_asset = {}
            texture_asset["type"] = "texture"
            texture_asset["name"] = texture['name']
            texture_asset["path"] = "Textures/" + texture['system_name'] + texture['extension']
            exported["assets"].append(texture_asset)
            generated_textures.append(texture['name'])

            if context.scene.shatter_export_textures == True:
                ExportTexture(context, texture, texture_asset)

        if context.scene.shatter_export_meshes == False:
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
            'use_tspace': False, 
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

        keywords["context_objects"] = [obj]

        try:
            depsgraph = context.evaluated_depsgraph_get()
            export_path = bpy.path.abspath(context.scene.shatter_game_path + asset["path"])
            export_fbx_bin.save_single(operator, context.scene, depsgraph, export_path, **keywords)
        except:
            print("Something went oopsie.")
        
        obj.matrix_world = original_matrix
        bpy.context.view_layer.update()

def ParseObject(operator,context,exported, obj, recurse = True, parent = None):
    if obj.shatter_export == False:
        return

    for collection in obj.users_collection:
        if collection.name in context.view_layer.layer_collection.children:
            view_collection = context.view_layer.layer_collection.children[collection.name]
            if view_collection.hide_viewport == True or collection.hide_render == True:
                return
    
    GenerateAsset(operator,context,exported,obj)

    shatter_name = obj.get("shatter_name", obj.name)
    shatter_type = obj.shatter_type
    if obj.type == "EMPTY":
        if obj.instance_type == "COLLECTION" and recurse:
            print("Collection: " + obj.name + " (" + str(len(obj.instance_collection.objects)) + ")")

            if len(obj.shatter_prefab) > 0:
                print("Prefab path: " + obj.shatter_prefab)
                obj.shatter_type = "level"
            else:
                for child in obj.instance_collection.objects:
                    ParseObject(operator,context,exported,child, False, obj)
            print("End of Collection: " + obj.name)
        else:
            print("Unknown empty type. (" + obj.instance_type + ")")

    if len(obj.shatter_type) > 0:
        # print("Shatter Type: " + obj.shatter_type)
        entity = {}

        name_prefix = ""
        if parent and parent.shatter_type == "level":
            name_prefix = parent.get("shatter_name", parent.name)

        if obj.shatter_type != "level":
            entity["name"] = name_prefix + shatter_name

            if len(obj.shatter_uuid) == 0:
                obj.shatter_uuid = str( uuid.uuid4() )

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
            print("Prefab sub-level " + obj.shatter_prefab)
            entity["path"] = obj.shatter_prefab + ".sls"

        # Fetch the mesh name if we're a mesh object.
        if entity["type"] == "mesh" and obj.type == "MESH":
            # print("Mesh " + obj.data.name)
            entity["mesh"] = obj.data.name.lower()
        elif not is_level:
            print("Object " + obj.name)
            entity["mesh"] = obj.name.lower()

        if not is_level:
            entity["shader"] = "DefaultGrid"

            texture = GetTexture(obj)
            if texture != None:
                entity["texture"] = texture['name']
                entity["shader"] = "DefaultTextured"
            else:
                entity["texture"] = "error"

        original_matrix = copy.deepcopy(obj.matrix_world)
        original_color = obj.color
        if parent != None:
            obj.matrix_world = parent.matrix_world @ obj.matrix_world
            obj.color[0] = parent.color[0]
            obj.color[1] = parent.color[1]
            obj.color[2] = parent.color[2]

        position = copy.deepcopy(obj.location)
        
        entity["position"] = VectorToString(position)
        # entity["position"] = "0 0 0"

        rotation = copy.deepcopy(obj.rotation_euler)

        rotation.x = degrees(obj.rotation_euler.y)
        rotation.y = degrees(obj.rotation_euler.x)
        rotation.z = degrees(obj.rotation_euler.z)

        entity["rotation"] = VectorToString(rotation)
        # entity["rotation"] = "0 0 0"
        entity["scale"] = VectorToString(obj.scale)

        if not is_level and obj.shatter_type != "custom" and obj.type != "EMPTY":
            entity["color"] = VectorToString(obj.color)
            entity["visible"] = "1" if obj.shatter_visible else "0"
            entity["collision"] = "1" if obj.shatter_collision else "0"
            entity["collisiontype"] = collision_types[obj.shatter_collision_type]
            if obj.shatter_collision:
                entity["static"] = "1"
                entity["stationary"] = "0"
        
        additional_key_values = obj.shatter_key_values
        for pair in additional_key_values:
            entity[pair.name] = pair.value

        if parent:
            additional_key_values = parent.shatter_key_values

        for pair in additional_key_values:
            entity[pair.name] = pair.value

        for pair in obj.shatter_properties:
            entity[pair.name] = GetPropertyValue(pair)


        exported["entities"].append(entity)

        obj.matrix_world = original_matrix
        obj.color = original_color

def ExportObjects(operator,context):
    objects = context.scene.objects

    ResetExporter()

    exported = {
        "version" : "0",
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

        sky = {}
        sky["name"] = "sky"
        sky["type"] = "sky"
        sky["mesh"] = "sky"
        sky["shader"] = "sky"
        sky["texture"] = "sky"
        sky["position"] = "0 0 0"
        sky["rotation"] = "0 0 0"
        sky["scale"] = "1900 1900 1900"
        exported["entities"].append(sky)

    for obj in objects:
        ParseObject(operator,context,exported,obj)

    print("Configured " + str(len(exported["assets"])) + " assets.")
    print("Configured " + str(len(exported["entities"])) + " entities.")

    return exported

class ExportScene(bpy.types.Operator):
    bl_idname = "shatter.export_scene"
    bl_label = "Export"
    bl_description = "Exports the current scene to a Shatter level file"

    def execute(self,context):
        exported = ExportObjects(self,context)
        export_path = context.scene.shatter_export_path + context.scene.name + ".sls"
        full_path = bpy.path.abspath(export_path)
        self.report({"INFO"}, "Exporting to " + export_path)

        export_file = open(full_path, 'w')
        json.dump(exported, export_file, indent=4)

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

        subprocess.Popen([
            full_path, 
            "-world",level_path + context.scene.name, 
            "-x", x, "-y", y, "-z", z
            #"-dirx", dirx, "-diry", diry, "-dirz", dirz
            ], cwd=working_directory)

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
        row.prop(scene, "shatter_export_prefabs")
        row.prop(scene, "shatter_export_meshes")
        #row = layout.row()
        row.prop(scene, "shatter_export_textures")

        row.prop(scene, "shatter_is_bare")

        row = layout.row()
        row.operator("shatter.export_scene", icon="EXPORT")

        row = layout.row()
        row.operator("shatter.run_world", icon="TEXT")

        row = layout.row()
        row.operator("shatter.export_scene_run_world", icon="PLAY")

        json_only = scene.shatter_export_prefabs == False and scene.shatter_export_meshes == False and scene.shatter_export_textures == False
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

    if obj.shatter_type not in bpy.types.Scene.shatter_definitions:
        if clear == True:
            obj.shatter_properties.clear()
        return

    if clear == True:
        obj.shatter_properties.clear()

    definitions = bpy.types.Scene.shatter_definitions[obj.shatter_type]

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
                if definition["key"] == prop.name:
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
        item.prop = StringProperty(name=item.name)

def OnTypeUpdate(self,context):
    ApplyDefinition(self)

class LoadDefinitions(bpy.types.Operator):
    bl_idname = "shatter.load_definitions"
    bl_label = "Reload Definitions"
    bl_description = "Loads entity definitions if available."

    filtered_keys = ["name", "transform", "inputs", "outputs"]

    def execute(self,context):
        definitions_path = bpy.path.abspath(context.scene.shatter_game_path + "Definitions.fgd")

        if not os.path.isfile(definitions_path):
            print("No definitions file found. (" + definitions_path + ")")
            return {'FINISHED'}

        with open(definitions_path) as definition_file:
            print("Loading definitions. (" + definitions_path + ")")
            definitions = json.load(definition_file)
            if "types" in definitions:
                entity_meta = {}
                entity_types = []

                entity_types.append(("mesh", "Mesh",""))
                entity_types.append(("level", "Level",""))
                entity_types.append(("custom", "Custom",""))

                native_types = len(entity_types)

                for item in definitions["types"]:
                    if "name" in item:
                        entity_types.append((item["name"],item["name"].capitalize(),""))

                        for meta in item.items():
                            data = {}

                            key = meta[0]
                            type = meta[1]

                            if key in self.filtered_keys:
                                continue

                            data["key"] = key
                            data["type"] = type

                            if item["name"] not in entity_meta:
                                entity_meta[item["name"]] = []

                            entity_meta[item["name"]].append(data)

                entity_types = tuple(entity_types)

                if bpy.types.Scene.shatter_definitions:
                    del bpy.types.Scene.shatter_definitions
                bpy.types.Scene.shatter_definitions = entity_meta

                additional_types = len(entity_types) - native_types
                print(str(additional_types) + " additional types found.")
                print(str(len(entity_meta)) + " meta types.")

                if bpy.types.Object.shatter_type:
                    del bpy.types.Object.shatter_type

                bpy.types.Object.shatter_type = EnumProperty(
                    items=entity_types,
                    name="Type",
                    description="Entity descriptors",
                    update=OnTypeUpdate
                    )

        self.ApplyDefinitions(context)

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

    #for i in range(0,1000):
    #    entity_types.append(("unknown", "Unknown descriptor",""))

    return tuple(entity_types)

# Getters are required if a setter exists.
def GetPrefab(self):
    return self["shatter_prefab"]

# Used to set the prefab path to its relative directory
def SetPrefab(self, value):
    game_path = bpy.path.abspath(bpy.context.scene.shatter_game_path)

    # Get the path relative to the game path.
    value = bpy.path.relpath(bpy.path.abspath(value), game_path)

    # Remove the extra slashes at the start.
    value = value.lstrip('/')

    # Replace the backslashes with forward slashes if needed.
    value = value.replace('\\','/')

    # Strip the extension.
    value = value.rstrip(".sls")

    self["shatter_prefab"] = value

classes = (
    KeyValueItem,
    SLSS_UL_KeyValueList,

    ObjectValueItem,
    SLSS_UL_ObjectList,
    ShatterObjectAdd,
    ShatterObjectRemove,
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

def RegisterScenePanels():
    # Register all of the classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    Scene = bpy.types.Scene

    # Register scene panel properties.
    Scene.shatter_export_path = StringProperty(name="Levels Path",description="Export location of the main level file", subtype="DIR_PATH")
    Scene.shatter_game_path = StringProperty(name="Game Path",description="Location of the game's executable", subtype="DIR_PATH", update=OnGamePathUpdate)
    Scene.shatter_game_executable = StringProperty(name="Game Executable",description="Name of the game's executable")
    Scene.shatter_export_prefabs = BoolProperty(name="Prefabs",description="Determines whether proxies marked as prefabs should be exported",default=False)
    Scene.shatter_export_meshes = BoolProperty(name="Meshes",description="Determines whether meshes should be exported",default=True)
    Scene.shatter_export_textures = BoolProperty(name="Textures",description="Determines whether textures should be exported",default=True)

    Scene.shatter_is_bare = BoolProperty(name="Bare",description="Bare files don't include things like the sky mesh by default.",default=True)

    Scene.shatter_definitions = []

    # Register object properties.
    Object = bpy.types.Object
    Object.shatter_collision = BoolProperty(name="Collision",description="Enables collisions for this object.",default=True)
    Object.shatter_collision_type = EnumProperty(
        items=(
            ("shatter_collision_triangle", "Triangle Mesh", "Use triangle mesh collision tests."),
            ("shatter_collision_aabb", "Bounding Box", "Use AABB collision tests."),
            ("shatter_collision_plane", "Planar", "Use plane collision tests.")
        ),
        name="Collision Type",
        description="Should this object be visible in the engine?"
        )

    Object.shatter_type = EnumProperty(
        items=GetDummyEntityList(),
        name="Entity",
        description="",
        update=OnTypeUpdate
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

    Object.shatter_key_values = CollectionProperty(type = KeyValueItem)
    Object.shatter_key_value_index = IntProperty(name="Key Value Index", default=0)

    Object.shatter_properties = CollectionProperty(type = DefinitionType)

    Object.shatter_visible = BoolProperty(name="Visible",description="Should this object be visible in the engine?",default=True)
    Object.shatter_export = BoolProperty(name="Export",description="When disabled, this object is never exported.",default=True)

    Object.shatter_prefab = StringProperty(name="Prefab",description="Where to look for the prefab if relevant.", subtype="FILE_PATH", get=GetPrefab, set=SetPrefab)
    Object.shatter_uuid = StringProperty(name="UUID",description="Unique identifier for the Shatter engine.")

    bpy.app.handlers.load_post.append(InitializeDefinitions)

    # Use a timer to prod the operator, it's not possible to execute it straight away.
    Timer(0.1, InitializeDefinitions, ["test"]).start()

def UnregisterScenePanels():
    # Unregister all of the classes
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.app.handlers.load_post.remove(InitializeDefinitions)

    Scene = bpy.types.Scene

    # Unregister scene panel properties.
    del Scene.shatter_export_path
    del Scene.shatter_game_path
    del Scene.shatter_game_executable
    del Scene.shatter_export_prefabs
    del Scene.shatter_export_meshes
    del Scene.shatter_export_textures

    del Scene.shatter_is_bare

    del Scene.shatter_definitions

    Object = bpy.types.Object

    # Unregister object properties.
    del Object.shatter_collision
    del Object.shatter_collision_type
    del Object.shatter_type
    del Object.shatter_type_custom

    del Object.shatter_shader_type
    del Object.shatter_shader_type_custom

    del Object.shatter_key_values
    del Object.shatter_key_value_index
    del Object.shatter_properties

    del Object.shatter_visible
    del Object.shatter_export

    del Object.shatter_prefab
    del Object.shatter_uuid