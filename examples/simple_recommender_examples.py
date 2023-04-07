import subprocess
import common

# All from same repo
subprocess.run(["/usr/bin/python3", common.path_relative_to_root("recommender/simple_recommender.py"), "I1d148e18d81d1122838b9dc7e994190f4e796ddf", "Idd046451f9ce6095b6fa31c0b9820541544e5077", "--repository", "mediawiki/extensions/CheckUser"], cwd=common.path_relative_to_root(""))

# From multiple repos
subprocess.run(["/usr/bin/python3", common.path_relative_to_root("recommender/simple_recommender.py"), "Ifd3936b0c0e58450c034a8f69a69b1d8ea82bd65", "Ib01ab1e90b491881a864ef67d2ed93f624a7b7f0", "--repository", "mediawiki/extensions/CheckUser", "mediawiki/extensions/MassMessage"], cwd=common.path_relative_to_root(""))