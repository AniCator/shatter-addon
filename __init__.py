bl_info = {
    "name" : "Blender2Shatter - Shatter Engine Exporter",
    "author" : "AniCator",
    "description" : "Exporter that is used to export level and mesh data to a format the Shatter Engine understands.",
    "blender" : ( 2, 80, 0 ),
    "location" : "File > Import/Export, Scene properties",
    "warning" : "Experimental",
    "category" : "Import-Export"
}

import bpy

from . scene_panel import RegisterScenePanels, UnregisterScenePanels

from . dialogue_node_tree import RegisterDialogueTree, UnregisterDialogueTree

def register():
    RegisterScenePanels()
    RegisterDialogueTree()



def unregister():
    UnregisterScenePanels()
    UnregisterDialogueTree()


if __name__ == "__main__":
    register()