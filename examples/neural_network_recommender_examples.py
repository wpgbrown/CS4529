import subprocess
import common
import os

# TODO: Expand examples to include features specific to the neural network implementation (e,g, using repo-specific, generic and status models)

# One from one repo
print("Example 1: One change from the CheckUser extension")
subprocess.run(["/usr/bin/python3", common.path_relative_to_root("recommender/neural_network_recommender/neural_network_recommender.py"), "I1d148e18d81d1122838b9dc7e994190f4e796ddf", "--repository", "mediawiki/extensions/CheckUser", "--stats"], cwd=common.path_relative_to_root(""))

input("Press enter to continue:")
os.system('cls' if os.name == 'nt' else 'clear')
print("Example 2: Two changes from CheckUser repository")
# Two from same repo
subprocess.run(["/usr/bin/python3", common.path_relative_to_root("recommender/neural_network_recommender/neural_network_recommender.py"), "I2a6237a8174dbd3c115e6b70a056331811be9e03", "Idd046451f9ce6095b6fa31c0b9820541544e5077", "--repository", "mediawiki/extensions/CheckUser", "--stats"], cwd=common.path_relative_to_root(""))

input("Press enter to continue:")
os.system('cls' if os.name == 'nt' else 'clear')
print("Example 3: Two changes each from a different repository")
# From multiple repos
subprocess.run(["/usr/bin/python3", common.path_relative_to_root("recommender/neural_network_recommender/neural_network_recommender.py"), "Ifd3936b0c0e58450c034a8f69a69b1d8ea82bd65", "Ib01ab1e90b491881a864ef67d2ed93f624a7b7f0", "--repository", "mediawiki/extensions/CheckUser", "mediawiki/extensions/MassMessage", "--stats"], cwd=common.path_relative_to_root(""))