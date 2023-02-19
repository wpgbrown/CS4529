import json
import re

from data_collection import common

with open("raw_data/groups_list.json", "r") as f:
    with open("raw_data/extension_groups_list.json", "w") as f2:
        extension_groups = {}
        groups = json.load(f)
        group_names = groups.keys()
        for extension in common.extensions_list:
            if extension in group_names:
                extension_groups[extension] = groups[extension]
            elif "extension-" + extension in group_names:
                extension_groups[extension] = groups["extension-" + extension]
            else:
                for group in group_names:
                    if extension in group:
                        print("Here: " + extension + "   " + group)
        json.dump( extension_groups, f2 )