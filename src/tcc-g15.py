# (c) github.com/AlexIII
# GPLv3

import sys
from GUI.AppGUI import runApp
# from pyuac import main_requires_admin

# @main_requires_admin
def main():
    return runApp()

if __name__ == "__main__":
    print("Starting")
    sys.exit(main())
