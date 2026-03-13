import PyInstaller.__main__
import os

if __name__ == '__main__':
    print("Packaging Timesheet Tracker using PyInstaller...")

    app_mode = os.environ.get("APP_MODE", "production").strip().lower()
    exe_name = "timesheet-test" if app_mode in {"testing", "test"} else "timesheet"
    
    # We require the Vite output folder to avoid bundling stale legacy builds
    ui_folder_candidates = ["../frontend/dist", "Timesheet/dist"]
    ui_folder = next((p for p in ui_folder_candidates if os.path.exists(p)), None)

    if not ui_folder:
        print("ERROR: React UI dist folder not found! Please run 'npm run build' inside the Timesheet directory first.")
        exit(1)

    PyInstaller.__main__.run([
        'run.py',                         # Main entry point triggering pywebview
        f'--name={exe_name}',             # Name of the exe
        '--windowed',                     # No console window
        '--onefile',                      # Build a single executable file
        '--noconfirm',                    # Overwrite existing dist/build folders
        '--clean',                        # Clean cache
        
        # Include static files
        f'--add-data={ui_folder};ui',     # Includes UI files into the 'ui' virtual folder
        
        # Explicit python module imports to ensure FastAPI and uvicorn are bundled correctly
        '--hidden-import=uvicorn.logging',
        '--hidden-import=uvicorn.loops',
        '--hidden-import=uvicorn.loops.auto',
        '--hidden-import=uvicorn.protocols',
        '--hidden-import=uvicorn.protocols.http',
        '--hidden-import=uvicorn.protocols.http.auto',
        '--hidden-import=uvicorn.protocols.websockets',
        '--hidden-import=uvicorn.protocols.websockets.auto',
        '--hidden-import=uvicorn.lifespan',
        '--hidden-import=uvicorn.lifespan.on',
        
        # Make sure our database backend loads correctly
        '--hidden-import=database',
        '--hidden-import=api',
        '--hidden-import=pdf_export',
        '--hidden-import=reportlab',
    ])
    
    print("\n--- Packaging Complete ---")
    print("Your app should be located in the 'dist' folder!")
