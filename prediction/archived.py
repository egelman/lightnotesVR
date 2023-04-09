import subprocess
import psutil
import datetime

def get_installed_apps_by_process():
    installed_apps = subprocess.check_output(["/usr/bin/mdfind", "kMDItemContentType == 'com.apple.application-bundle'"]).decode().split("\n")

    # Filter the installed applications by their bundle ID and retrieve their displayed name
    app_names = []
    for app in installed_apps:
        if app.startswith("/Applications"):
            try:
                app_name = subprocess.check_output(["/usr/bin/defaults", "read", app + "/Contents/Info.plist", "CFBundleDisplayName"], stderr=subprocess.DEVNULL).decode().strip()
                app_names.append(app_name)
            except:
                continue
    app_names.sort()
    return app_names

def test_if_application_is_running(name):
    is_running = False
    creation_time = None
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        if proc.info["name"] == name:
            is_running = True
            creation_time = datetime.datetime.fromtimestamp(proc.info["create_time"]).strftime("%Y-%m-%d %H:%M:%S")
            break

    print(name, "is running" if is_running else "is not running", "and was last opened on", creation_time if creation_time else "N/A")
    return is_running