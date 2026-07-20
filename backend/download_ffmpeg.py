import os
import sys
import urllib.request
import zipfile
import shutil

def download_ffmpeg():
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
    ffmpeg_exe = os.path.join(bin_dir, 'ffmpeg.exe')
    ffprobe_exe = os.path.join(bin_dir, 'ffprobe.exe')

    if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
        print("FFmpeg and FFprobe are already installed locally.")
        return ffmpeg_exe, ffprobe_exe

    os.makedirs(bin_dir, exist_ok=True)
    
    # Official build from gyan.dev
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_path = os.path.join(bin_dir, "ffmpeg.zip")

    print("Downloading FFmpeg (this might take a few moments)...")
    try:
        urllib.request.urlretrieve(url, zip_path)
        print("Download complete. Extracting files...")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Find the ffmpeg.exe and ffprobe.exe in the zip
            for file in zip_ref.namelist():
                if file.endswith('ffmpeg.exe'):
                    with zip_ref.open(file) as source, open(ffmpeg_exe, 'wb') as target:
                        shutil.copyfileobj(source, target)
                elif file.endswith('ffprobe.exe'):
                    with zip_ref.open(file) as source, open(ffprobe_exe, 'wb') as target:
                        shutil.copyfileobj(source, target)
                        
        print("Extraction complete. Cleaning up...")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        print("FFmpeg successfully set up in backend/bin/")
        return ffmpeg_exe, ffprobe_exe
    except Exception as e:
        print(f"Error setting up FFmpeg: {e}")
        return None, None

if __name__ == '__main__':
    download_ffmpeg()
