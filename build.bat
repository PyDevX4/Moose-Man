@echo off
python -m PyInstaller --noconfirm --onefile --windowed --name "Moose Man" --paths src --hidden-import glcontext --collect-submodules glcontext --distpath . src\game.py
