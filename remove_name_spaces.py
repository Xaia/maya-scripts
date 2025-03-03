import maya.cmds as cmds

def remove_all_namespaces():
    """
    Removes all non-default namespaces in the Maya scene by merging their contents
    into the root namespace.
    """
    # Get a list of all namespaces in the scene
    namespaces = cmds.namespaceInfo(listOnlyNamespaces=True) or []
    
    # Define namespaces that should not be removed
    default_namespaces = ['UI', 'shared']
    
    for ns in namespaces:
        if ns in default_namespaces:
            continue
        try:
            # Merge all nodes from the namespace into the root and remove the namespace
            cmds.namespace(removeNamespace=ns, mergeNamespaceWithRoot=True)
            print("Removed namespace: {}".format(ns))
        except Exception as e:
            print("Failed to remove namespace '{}': {}".format(ns, e))

# Run the function
remove_all_namespaces()
