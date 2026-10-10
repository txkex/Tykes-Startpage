# Double-click to run the start page on Windows with no console window.
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py"), run_name="__main__")
