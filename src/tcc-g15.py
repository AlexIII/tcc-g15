# (c) github.com/AlexIII
# GPLv3

import sys
from GUI.AppGUI import runApp, errorExit
# from pyuac import main_requires_admin

def createAppLockFile():
    # works for windows only
    import tempfile
    import os
    basename = (
        os.path.splitext(os.path.abspath(sys.argv[0]))[0]
            .replace("/", "-").replace(":", "").replace("\\", "-")
            + ".lock"
    )
    lockfile = os.path.normpath(tempfile.gettempdir() + "/" + basename)
    if os.path.exists(lockfile):
        os.unlink(lockfile)
    os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        

# @main_requires_admin
def main():
    try:
        createAppLockFile()
    except:
        errorExit("Another instance of this app is already running")
        return 1
    return runApp()

if __name__ == "__main__":
    print("Starting")
    sys.exit(main())
