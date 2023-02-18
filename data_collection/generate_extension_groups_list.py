import json
from . import common

with open("groups_list.json", "r") as f:
    with open("extension_groups_list.txt", "w") as f2:
        extension_groups = {}
        groups = json.load(f)
        group_names = groups.keys()
        for extension in common.extensions_list:
            if extension in group_names:
                extension_groups[extension] = groups[extension]
            elif "extension-" + extension in group_names:
                extension_groups[extension] = groups["extension-" + extension]
        print(groups.keys())