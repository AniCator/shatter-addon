# the little less documented way of adding a custom node tree
#   and populate it with nodes of varying types of I/O
#   sockets that work together, discombobulated

import bpy


class DialogueNodeTree(bpy.types.NodeTree):
    '''Dialogue editor that allows for visual scripting of dialogue sequences'''
    bl_idname='DialogueNodeTree'
    bl_label='Dialogue Editor'
    bl_icon='OUTLINER_OB_FONT'

    def update(self):
        
        # Don't allow links of the same type to connect to each other.
        for link in self.links:
            same_type = isinstance(link.from_node, type(link.to_node))
            if same_type:
                self.links.remove(link)

        return

class DialogueSocket(bpy.types.NodeSocket):
    bl_idname = "DialogueSocket"
    bl_label = "Dialogue Socket"
    prop_name = bpy.props.StringProperty(default='')
    socket_col = bpy.props.FloatVectorProperty(size=4, default=(1, 1, 1, 1))

    type = 'CUSTOM'
    link_limit = 500

    def draw(self, context, layout, node, text):
        return

    def draw_color(self, context, node):
        if self.is_linked:
            return (0,0.75,0,1)
        else:
            return (0.75,0,0,1)

    
class CustomNode(bpy.types.Node):
    @classmethod
    def poll(self, ntree):
        return ntree.bl_idname == 'DialogueNodeTree'


class DialogueBodyNode(CustomNode):
    '''Dialogue body node'''
    bl_idname = 'DialogueBodyNode'
    bl_label = 'Cue'
    # bl_icon = 'ADD'
    
    Name : bpy.props.StringProperty()
    Target : bpy.props.PointerProperty(type=bpy.types.Object)
    Body : bpy.props.StringProperty()
    
    def init(self, context):
        self.outputs.new('DialogueSocket', "")
        self.inputs.new('DialogueSocket',"")
        
    #def copy(self, node):
    #    print("copied node", node)
        
    #def free(self):
    #    print("Node removed", self)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, 'Name')
        layout.prop(self, 'Target')
        layout.prop(self, 'Body')
    
class DialogueChoiceNode(CustomNode):
    bl_idname = "DialogueChoiceNode"
    bl_label = "Choice"

    body : bpy.props.StringProperty(name="Body")

    def init(self, context):
        self.outputs.new('DialogueSocket', "")
        self.inputs.new('DialogueSocket',"")

    def update(self):
        self.color = (0,1,0)
        self.use_custom_color=False
        self.width=200.0

    def draw_buttons(self, context, layout):
        layout.prop(self, 'body')


import nodeitems_utils

class DialogueNodeCategory(nodeitems_utils.NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'DialogueNodeTree'
    

# make a list of node categories for registration
node_categories = [
    DialogueNodeCategory("DIALOGUENODES", "Dialogue", items=[
        nodeitems_utils.NodeItem("DialogueBodyNode"),
        nodeitems_utils.NodeItem("DialogueChoiceNode")
        ]),
]



classes=(
        DialogueNodeTree,
        DialogueSocket,
        DialogueBodyNode,
        DialogueChoiceNode
    )
    
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    nodeitems_utils.register_node_categories("DIALOGUE_NODES", node_categories)


# for unloading we define the unregistering of all defined classes
def unregister():
    nodeitems_utils.unregister_node_categories("DIALOGUE_NODES")

    for cls in classes:
        bpy.utils.unregister_class(cls)

def UnregisterDialogueTree():
    unregister()

def RegisterDialogueTree():
    try:
        nodeitems_utils.unregister_node_categories("DIALOGUE_NODES")
    except:
        pass

    register()
        