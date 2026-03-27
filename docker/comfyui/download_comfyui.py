"""Download ComfyUI from GitHub as a tarball — no git or apt-get required."""
import os
import shutil
import tarfile
import urllib.request

url = "https://github.com/comfyanonymous/ComfyUI/archive/refs/heads/master.tar.gz"
dest = "/tmp/comfyui.tar.gz"
extract_dir = "/tmp"
src = "/tmp/ComfyUI-master"
app_dir = "/app"

print(f"Downloading ComfyUI from {url} ...")
urllib.request.urlretrieve(url, dest)

print("Extracting...")
t = tarfile.open(dest)
t.extractall(extract_dir)
t.close()

print(f"Moving files to {app_dir} ...")
for name in os.listdir(src):
    shutil.move(os.path.join(src, name), os.path.join(app_dir, name))

os.remove(dest)
shutil.rmtree(src, ignore_errors=True)
print("Done.")
