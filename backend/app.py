import sys
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from PIL import Image

app = FastAPI(title="Swiss Backend API")

# Allow CORS since Electron or local browser is serving files locally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

import platform
import subprocess

@app.get("/api/system/info")
def get_system_info():
    # Check if FFmpeg exists
    bin_dir = os.path.join(os.path.dirname(__file__), "bin")
    ffmpeg_exe = os.path.join(bin_dir, "ffmpeg.exe")
    ffmpeg_exists = os.path.exists(ffmpeg_exe)
    
    # Try to get ffmpeg version
    ffmpeg_version = "Unbekannt"
    if ffmpeg_exists:
        try:
            res = subprocess.run([ffmpeg_exe, "-version"], capture_output=True, text=True)
            first_line = res.stdout.split('\n')[0]
            ffmpeg_version = first_line.split('Copyright')[0].strip()
        except Exception:
            ffmpeg_version = "Installiert (Fehler beim Lesen der Version)"

    return {
        "success": True,
        "os": platform.system(),
        "os_release": platform.release(),
        "python_version": platform.python_version(),
        "ffmpeg_status": "Bereit" if ffmpeg_exists else "Fehlt (Video-Tools deaktiviert)",
        "ffmpeg_path": os.path.abspath(ffmpeg_exe) if ffmpeg_exists else "Fehlt",
        "ffmpeg_version": ffmpeg_version,
        "backend_dir": os.path.abspath(os.path.dirname(__file__))
    }

@app.post("/api/system/download-ffmpeg")
async def download_ffmpeg_api():
    try:
        script_path = os.path.join(os.path.dirname(__file__), "download_ffmpeg.py")
        res = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
        if res.returncode == 0:
            return {"success": True, "detail": "FFmpeg erfolgreich heruntergeladen!"}
        else:
            raise HTTPException(status_code=500, detail=res.stderr or "Fehler beim Ausführen des Skripts")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from typing import Optional

import io

@app.post("/api/image/convert")
async def convert_image(
    file: UploadFile = File(...),
    output_format: str = Form(...),
    quality: int = Form(80),
    output_dir: Optional[str] = Form(None)
):
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))

        # --- ICO INPUT: pick the largest embedded icon frame ---
        original_filename = file.filename if file.filename else "image"
        if original_filename.lower().endswith('.ico') or getattr(img, 'format', '') == 'ICO':
            try:
                # Try to find and use the largest available size
                sizes = img.info.get('sizes', [])
                if sizes:
                    largest = max(sizes, key=lambda s: s[0] * s[1])
                    img.size = largest
                img = img.convert('RGBA')  # ICO frames are usually RGBA
            except Exception:
                img = img.convert('RGBA')
        
        # Determine target file name
        base_name = os.path.splitext(os.path.basename(original_filename))[0]
        ext = output_format.lower()
        if ext == "jpeg":
            ext = "jpg"
            
        # Fallback to User Downloads if no output_dir specified
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        target_path = os.path.join(target_dir, f"{base_name}_converted.{ext}")
        
        # Convert color profiles if converting from RGBA to RGB formats like JPEG
        if img.mode in ("RGBA", "LA") and ext in ("jpg", "jpeg", "bmp"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB" and ext in ("jpg", "jpeg", "bmp"):
            img = img.convert("RGB")
            
        # Save options
        save_kwargs = {}
        if ext in ("jpg", "jpeg", "webp"):
            save_kwargs["quality"] = quality
        
        # --- ICO OUTPUT: Pillow requires explicit sizes ---
        if ext == "ico":
            w, h = img.size
            ico_sizes = [(s, s) for s in [16, 32, 48, 64, 128, 256] if s <= min(w, h)]
            if not ico_sizes:
                ico_sizes = [(min(w, h), min(w, h))]
            save_kwargs["sizes"] = ico_sizes
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            
        img.save(target_path, **save_kwargs)
        
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from typing import List
from pypdf import PdfWriter, PdfReader
import fitz  # PyMuPDF

@app.post("/api/pdf/merge")
async def pdf_merge(
    files: List[UploadFile] = File(...),
    output_dir: Optional[str] = Form(None)
):
    try:
        writer = PdfWriter()
        for file in files:
            content = await file.read()
            pdf_file = io.BytesIO(content)
            writer.append(pdf_file)
            
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        target_path = os.path.join(target_dir, "merged_document.pdf")
        
        with open(target_path, "wb") as out:
            writer.write(out)
            
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/split")
async def pdf_split(
    file: UploadFile = File(...),
    pages: str = Form(...),  # e.g., "1-3, 5, 7-end"
    output_dir: Optional[str] = Form(None)
):
    try:
        content = await file.read()
        reader = PdfReader(io.BytesIO(content))
        writer = PdfWriter()
        total_pages = len(reader.pages)
        
        # Parse page string (1-indexed for user, 0-indexed for code)
        selected_indices = []
        parts = pages.replace(" ", "").split(",")
        for part in parts:
            if "-" in part:
                start, end = part.split("-")
                start_idx = int(start) - 1
                end_idx = total_pages if end.lower() == "end" else int(end)
                selected_indices.extend(range(start_idx, end_idx))
            else:
                selected_indices.append(int(part) - 1)
                
        # Append pages
        for idx in selected_indices:
            if 0 <= idx < total_pages:
                writer.add_page(reader.pages[idx])
                
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        original_name = os.path.splitext(file.filename)[0]
        target_path = os.path.join(target_dir, f"{original_name}_split.pdf")
        
        with open(target_path, "wb") as out:
            writer.write(out)
            
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/to-images")
async def pdf_to_images(
    file: UploadFile = File(...),
    output_dir: Optional[str] = Form(None)
):
    try:
        content = await file.read()
        doc = fitz.open(stream=content, filetype="pdf")
        
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        original_name = os.path.splitext(file.filename)[0]
        output_folder = os.path.join(target_dir, f"{original_name}_images")
        os.makedirs(output_folder, exist_ok=True)
        
        output_paths = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            img_path = os.path.join(output_folder, f"page_{i+1}.png")
            pix.save(img_path)
            output_paths.append(img_path)
            
        return {
            "success": True,
            "output_path": output_folder,
            "pages_exported": len(output_paths)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import subprocess

def get_ffmpeg_path():
    # Use bundled binaries if present, otherwise fall back to system path
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
    ffmpeg_local = os.path.join(bin_dir, 'ffmpeg.exe')
    if os.path.exists(ffmpeg_local):
        return ffmpeg_local
    return 'ffmpeg' # fallback to system

@app.post("/api/video/convert")
async def video_convert(
    file: UploadFile = File(...),
    output_format: str = Form(...),
    output_dir: Optional[str] = Form(None)
):
    try:
        # Save uploaded file temporarily to process it via ffmpeg
        temp_input = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"temp_{file.filename}")
        with open(temp_input, "wb") as f:
            f.write(await file.read())
            
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        original_name = os.path.splitext(file.filename)[0]
        ext = output_format.lower()
        target_path = os.path.join(target_dir, f"{original_name}_converted.{ext}")
        
        ffmpeg_cmd = get_ffmpeg_path()
        # Build command: overwrite target file, input file, default codecs (compatibility), output file
        cmd = [
            ffmpeg_cmd, "-y",
            "-i", temp_input,
            target_path
        ]
        
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        # Cleanup temp file
        if os.path.exists(temp_input):
            os.remove(temp_input)
            
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {process.stderr}")
            
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video/trim")
async def video_trim(
    file: UploadFile = File(...),
    start_time: str = Form(...),  # e.g., "00:00:10"
    duration: str = Form(...),    # e.g., "15" (seconds)
    output_dir: Optional[str] = Form(None)
):
    try:
        temp_input = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"temp_trim_{file.filename}")
        with open(temp_input, "wb") as f:
            f.write(await file.read())
            
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        original_name = os.path.splitext(file.filename)[0]
        ext = os.path.splitext(file.filename)[1].replace(".", "")
        target_path = os.path.join(target_dir, f"{original_name}_trimmed.{ext}")
        
        ffmpeg_cmd = get_ffmpeg_path()
        # Fast seeking with -ss before -i, copy codecs to avoid re-encoding
        cmd = [
            ffmpeg_cmd, "-y",
            "-ss", start_time,
            "-i", temp_input,
            "-t", duration,
            "-c", "copy",
            target_path
        ]
        
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        if os.path.exists(temp_input):
            os.remove(temp_input)
            
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {process.stderr}")
            
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video/to-gif")
async def video_to_gif(
    file: UploadFile = File(...),
    fps: int = Form(10),
    scale_width: int = Form(480),
    output_dir: Optional[str] = Form(None)
):
    try:
        temp_input = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"temp_gif_{file.filename}")
        with open(temp_input, "wb") as f:
            f.write(await file.read())
            
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        original_name = os.path.splitext(file.filename)[0]
        target_path = os.path.join(target_dir, f"{original_name}.gif")
        
        ffmpeg_cmd = get_ffmpeg_path()
        # High quality GIF palette filter setup
        filter_str = f"fps={fps},scale={scale_width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        
        cmd = [
            ffmpeg_cmd, "-y",
            "-i", temp_input,
            "-vf", filter_str,
            target_path
        ]
        
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        if os.path.exists(temp_input):
            os.remove(temp_input)
            
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {process.stderr}")
            
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

@app.post("/api/file/hash")
async def calculate_hash(
    file: UploadFile = File(...)
):
    try:
        content = await file.read()
        md5_hash = hashlib.md5(content).hexdigest()
        sha1_hash = hashlib.sha1(content).hexdigest()
        sha256_hash = hashlib.sha256(content).hexdigest()
        
        return {
            "success": True,
            "filename": file.filename,
            "md5": md5_hash,
            "sha1": sha1_hash,
            "sha256": sha256_hash,
            "size_bytes": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Derive keys securely for AES encryption
def get_key_from_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000
    )
    return kdf.derive(password.encode())

@app.post("/api/file/encrypt")
async def encrypt_file(
    file: UploadFile = File(...),
    password: str = Form(...),
    mode: str = Form(...), # "encrypt" or "decrypt"
    output_dir: Optional[str] = Form(None),
    extension: Optional[str] = Form("enc")
):
    try:
        content = await file.read()
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        original_name = file.filename
        ext = (extension or "enc").strip().replace(".", "")
        if not ext:
            ext = "enc"
        
        if mode == "encrypt":
            salt = os.urandom(16)
            iv = os.urandom(16)
            key = get_key_from_password(password, salt)
            
            # Padding block size (16 bytes for AES)
            pad_len = 16 - (len(content) % 16)
            padded_content = content + bytes([pad_len] * pad_len)
            
            encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
            ciphertext = encryptor.update(padded_content) + encryptor.finalize()
            
            # Output format: SALT(16B) + IV(16B) + CIPHERTEXT
            encrypted_data = salt + iv + ciphertext
            target_path = os.path.join(target_dir, f"{original_name}.{ext}")
            with open(target_path, "wb") as out:
                out.write(encrypted_data)
        else:
            # Decrypting
            if len(content) < 32:
                raise Exception("Encrypted file too short/corrupted")
                
            salt = content[:16]
            iv = content[16:32]
            ciphertext = content[32:]
            
            key = get_key_from_password(password, salt)
            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            padded_plain = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove padding
            pad_len = padded_plain[-1]
            if pad_len < 1 or pad_len > 16:
                raise Exception("Decryption failed (wrong password?)")
            plain = padded_plain[:-pad_len]
            
            ext_with_dot = f".{ext}"
            if original_name.lower().endswith(ext_with_dot.lower()):
                clean_name = original_name[:-len(ext_with_dot)] + "_decrypted"
            elif original_name.lower().endswith(".enc"):
                clean_name = original_name[:-4] + "_decrypted"
            else:
                name_part, ext_part = os.path.splitext(original_name)
                if ext_part:
                    clean_name = f"{name_part}_decrypted{ext_part}"
                else:
                    clean_name = f"{original_name}_decrypted"
                
            target_path = os.path.join(target_dir, clean_name)
            with open(target_path, "wb") as out:
                out.write(plain)
                
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": os.path.getsize(target_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def embed_message_in_wav(input_wav_bytes: bytes, secret_data: bytes) -> bytes:
    import wave
    import io
    import struct
    
    try:
        with wave.open(io.BytesIO(input_wav_bytes), "rb") as w:
            params = w.getparams()
            nchannels, sampwidth, framerate, nframes, comptype, compname = params
            frames = bytearray(w.readframes(nframes))
    except Exception as e:
        raise Exception(f"Fehler beim Lesen der WAV-Datei: {e}. Bitte stelle sicher, dass es sich um eine unkomprimierte WAV-Audiodatei handelt.")
    
    data_to_hide = struct.pack(">I", len(secret_data)) + secret_data
    required_samples = len(data_to_hide) * 8
    
    if len(frames) < required_samples:
        raise Exception(f"Audiodatei ist zu kurz. Benoetigt mindestens {required_samples} Bytes PCM, hat aber nur {len(frames)} Bytes.")
    
    total_bits = len(data_to_hide) * 8
    for i in range(total_bits):
        byte_index = i // 8
        bit_pos = 7 - (i % 8)
        bit = (data_to_hide[byte_index] >> bit_pos) & 1
        frames[i] = (frames[i] & 0xFE) | bit
        
    out_buf = io.BytesIO()
    with wave.open(out_buf, "wb") as w_out:
        w_out.setparams(params)
        w_out.writeframes(frames)
        
    return out_buf.getvalue()

def extract_message_from_wav(wav_bytes: bytes) -> bytes:
    import wave
    import io
    import struct
    
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            nframes = w.getnframes()
            frames = w.readframes(nframes)
    except Exception as e:
        raise Exception(f"Fehler beim Lesen der WAV-Datei: {e}")
        
    if len(frames) < 32:
        raise Exception("Ungueltiges WAV-Format oder Datei zu klein.")
        
    length_bytes = bytearray(4)
    for i in range(32):
        bit = frames[i] & 1
        byte_index = i // 8
        bit_pos = 7 - (i % 8)
        length_bytes[byte_index] |= (bit << bit_pos)
        
    length = struct.unpack(">I", length_bytes)[0]
    
    if length > (len(frames) - 32) // 8 or length < 0:
        raise Exception("Keine versteckte Nachricht in dieser Audiodatei gefunden oder Datei ist beschaedigt.")
        
    secret_data = bytearray(length)
    for i in range(32, 32 + length * 8):
        bit = frames[i] & 1
        data_index = (i - 32) // 8
        bit_pos = 7 - (i % 8)
        secret_data[data_index] |= (bit << bit_pos)
        
    return bytes(secret_data)

def encrypt_aes(data: bytes, password: str) -> bytes:
    import os
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    
    salt = os.urandom(16)
    iv = os.urandom(16)
    key = get_key_from_password(password, salt)
    
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len] * pad_len)
    
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return salt + iv + ciphertext

def decrypt_aes(encrypted_data: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    
    if len(encrypted_data) < 32:
        raise Exception("Verschluesselte Nachricht ist korrupt/zu kurz.")
    salt = encrypted_data[:16]
    iv = encrypted_data[16:32]
    ciphertext = encrypted_data[32:]
    
    key = get_key_from_password(password, salt)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    pad_len = padded_data[-1]
    if pad_len < 1 or pad_len > 16:
        raise Exception("Ungueltiges Passwort oder korrupte Daten.")
    return padded_data[:-pad_len]

@app.post("/api/audio/steg/encode")
async def audio_steg_encode(
    file: UploadFile = File(...),
    message: str = Form(...),
    password: Optional[str] = Form(None),
    output_dir: Optional[str] = Form(None)
):
    try:
        contents = await file.read()
        
        secret_bytes = message.encode("utf-8")
        if password:
            secret_bytes = encrypt_aes(secret_bytes, password)
            
        output_wav_bytes = embed_message_in_wav(contents, secret_bytes)
        
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        base_name = os.path.splitext(os.path.basename(file.filename))[0]
        target_path = os.path.join(target_dir, f"{base_name}_steg.wav")
        
        with open(target_path, "wb") as f_out:
            f_out.write(output_wav_bytes)
            
        return {
            "success": True,
            "output_path": target_path,
            "size_bytes": len(output_wav_bytes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audio/steg/decode")
async def audio_steg_decode(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None)
):
    try:
        contents = await file.read()
        extracted_bytes = extract_message_from_wav(contents)
        
        if password:
            extracted_bytes = decrypt_aes(extracted_bytes, password)
            
        try:
            decoded_text = extracted_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise Exception("Nachricht konnte nicht decodiert werden. Eventuell falsches Passwort oder keine Nachricht vorhanden.")
            
        return {
            "success": True,
            "message": decoded_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/directory/duplicates")
async def find_duplicates(
    directory_path: str = Form(...)
):
    if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
        raise HTTPException(status_code=400, detail="Invalid directory path")
        
    try:
        size_map = {}  # size_in_bytes -> list of file paths
        duplicates = []
        
        # 1. Group files by exact size (huge performance boost: unique sizes are skipped)
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    if size in size_map:
                        size_map[size].append(file_path)
                    else:
                        size_map[size] = [file_path]
                except:
                    continue  # Skip locked files/permission errors
                    
        # 2. For sizes with more than one file, verify identity using a composite hash
        for size, paths in size_map.items():
            if len(paths) <= 1:
                continue
                
            hash_groups = {} # hash -> list of paths
            for path in paths:
                try:
                    hasher = hashlib.md5()
                    # Add size to hash input
                    hasher.update(str(size).encode())
                    
                    if size <= 1024 * 1024:  # <= 1MB: read full file
                        with open(path, "rb") as f:
                            hasher.update(f.read())
                    else:  # > 1MB: sample first, middle, and last 256KB for speed and zero collisions
                        with open(path, "rb") as f:
                            # Start chunk
                            hasher.update(f.read(256 * 1024))
                            # Middle chunk
                            f.seek(size // 2)
                            hasher.update(f.read(256 * 1024))
                            # End chunk
                            f.seek(size - 256 * 1024)
                            hasher.update(f.read(256 * 1024))
                            
                    file_hash = hasher.hexdigest()
                    if file_hash in hash_groups:
                        hash_groups[file_hash].append(path)
                    else:
                        hash_groups[file_hash] = [path]
                except:
                    continue
            
            # Add verified duplicate groups
            for file_hash, dup_paths in hash_groups.items():
                if len(dup_paths) > 1:
                    duplicates.append({
                        "hash": file_hash,
                        "paths": dup_paths,
                        "count": len(dup_paths),
                        "size_bytes": size
                    })
                    
        return {
            "success": True,
            "directory": directory_path,
            "duplicates": duplicates,
            "total_groups": len(duplicates)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


import qrcode

@app.post("/api/quick/qr")
async def generate_qr(
    text: str = Form(...)
):
    try:
        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return {
            "success": True,
            "image_data": f"data:image/png;base64,{img_str}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/file/shred")
def shred_file(data: dict):
    file_path = data.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return {"success": False, "error": "Datei nicht gefunden"}
        
    try:
        size = os.path.getsize(file_path)
        
        # DoD 5220.22-M shredding standard (3 overwrite passes, rename, then delete)
        with open(file_path, "ba+", buffering=0) as f:
            # Pass 1: Zeros
            f.seek(0)
            f.write(b'\x00' * size)
            # Pass 2: Ones
            f.seek(0)
            f.write(b'\xff' * size)
            # Pass 3: Random
            f.seek(0)
            f.write(os.urandom(size))
            
        # Rename file to obscure original name in file tables
        import random
        dir_name = os.path.dirname(file_path)
        new_name = "".join(str(random.randint(0, 9)) for _ in range(12))
        new_path = os.path.join(dir_name, new_name)
        os.rename(file_path, new_path)
        
        # Delete file
        os.remove(new_path)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

from PIL.ExifTags import TAGS

@app.post("/api/image/metadata/read")
async def read_metadata(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))
        exif = img.getexif()
        
        metadata = {}
        # Extract common EXIF tags
        for tag_id in exif:
            tag = TAGS.get(tag_id, tag_id)
            value = exif.get(tag_id)
            if isinstance(value, bytes):
                try:
                    value = value.decode(errors="replace")
                except:
                    value = str(value)
            metadata[str(tag)] = str(value)
            
        return {
            "success": True,
            "filename": file.filename,
            "format": img.format,
            "width": img.width,
            "height": img.height,
            "metadata": metadata
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/image/metadata/write")
async def write_metadata(
    file: UploadFile = File(...),
    strip_all: bool = Form(False),
    tags_json: Optional[str] = Form(None),
    output_dir: Optional[str] = Form(None)
):
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))
        
        target_dir = output_dir if output_dir else os.path.expanduser("~/Downloads")
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        base_name = os.path.splitext(os.path.basename(file.filename))[0]
        ext = img.format.lower() if img.format else "png"
        target_path = os.path.join(target_dir, f"{base_name}_modified.{ext}")
        
        if strip_all:
            # Save completely clean image without metadata
            img.save(target_path, format=img.format)
        else:
            import json
            modified_tags = json.loads(tags_json) if tags_json else {}
            exif = img.getexif()
            
            # Map friendly tag names to EXIF tag IDs and update
            for name, val in modified_tags.items():
                for tag_id, tag_desc in TAGS.items():
                    if tag_desc == name:
                        exif[tag_id] = val
                        break
            
            img.save(target_path, format=img.format, exif=exif)
            
        return {"success": True, "target_path": target_path}
    except Exception as e:
        return {"success": False, "error": str(e)}

import time
import pyautogui

@app.post("/api/vault/autotype")
async def vault_autotype(
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        # Give the system 1 second to minimize the Electron window and restore focus to target
        time.sleep(1.0)
        
        # Write username, press tab, write password
        pyautogui.write(username, interval=0.01)
        pyautogui.press('tab')
        pyautogui.write(password, interval=0.01)
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── PRIVATE SPYWARE, TELEMETRY & PORT AUDITOR ENDPOINTS ───────────────────
import re

def check_telemetry_status():
    status = {
        "hosts_blocked": False,
        "diagtrack_disabled": False,
        "cortana_disabled": False,
        "bing_search_disabled": False
    }
    
    # 1. Check hosts file
    try:
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        if os.path.exists(hosts_path):
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if "vortex.data.microsoft.com" in content:
                    status["hosts_blocked"] = True
    except Exception:
        pass
        
    # 2. Check DiagTrack service
    try:
        res = subprocess.run(
            ["powershell", "-Command", "Get-Service -Name DiagTrack | Select-Object -ExpandProperty StartType"],
            capture_output=True, text=True, errors="ignore"
        )
        if "Disabled" in res.stdout:
            status["diagtrack_disabled"] = True
    except Exception:
        pass
        
    # 3. Check Cortana
    try:
        res = subprocess.run(
            ["powershell", "-Command", "Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search' -Name 'CortanaConsent' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CortanaConsent"],
            capture_output=True, text=True, errors="ignore"
        )
        if "0" in res.stdout or res.returncode != 0:
            status["cortana_disabled"] = True
    except Exception:
        pass

    # 4. Check Bing Search
    try:
        res = subprocess.run(
            ["powershell", "-Command", "Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search' -Name 'BingSearchEnabled' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty BingSearchEnabled"],
            capture_output=True, text=True, errors="ignore"
        )
        if "0" in res.stdout or res.returncode != 0:
            status["bing_search_disabled"] = True
    except Exception:
        pass
        
    return status

@app.get("/api/privacy/telemetry")
def get_telemetry_api():
    return {"success": True, "status": check_telemetry_status()}

@app.post("/api/privacy/telemetry/toggle")
async def toggle_telemetry_api(action: str = Form(...)):
    try:
        if action == "block":
            block_commands = """
            # 1. Edit hosts file safely (requires admin/write access)
            $hosts = "C:\\Windows\\System32\\drivers\\etc\\hosts"
            $domains = @("vortex.data.microsoft.com", "settings-win.data.microsoft.com", "telemetry.microsoft.com", "watson.telemetry.microsoft.com", "diagnostics.support.microsoft.com")
            if (Test-Path $hosts) {
                # Attempt to grant write permissions if blocked
                try {
                    $acl = Get-Acl $hosts
                    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule("Users","Write","Allow")
                    $acl.SetAccessRule($rule)
                    Set-Acl $hosts $acl
                } catch {}
                
                foreach ($d in $domains) {
                    if (!(Select-String -Path $hosts -Pattern $d -SimpleMatch)) {
                        Add-Content -Path $hosts -Value "`n0.0.0.0 $d"
                    }
                }
            }
            # 2. Disable DiagTrack
            Stop-Service -Name DiagTrack -Force -ErrorAction SilentlyContinue
            Set-Service -Name DiagTrack -StartupType Disabled -ErrorAction SilentlyContinue
            # 3. Disable Cortana & Bing search in Startmenu
            New-Item -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" -Force -ErrorAction SilentlyContinue | Out-Null
            Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" -Name "CortanaConsent" -Value 0 -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" -Name "BingSearchEnabled" -Value 0 -Force -ErrorAction SilentlyContinue
            """
            subprocess.run(["powershell", "-Command", block_commands], capture_output=True, text=True, errors="ignore")
        else:
            restore_commands = """
            $hosts = "C:\\Windows\\System32\\drivers\\etc\\hosts"
            if (Test-Path $hosts) {
                try {
                    $acl = Get-Acl $hosts
                    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule("Users","Write","Allow")
                    $acl.SetAccessRule($rule)
                    Set-Acl $hosts $acl
                } catch {}
                
                $content = Get-Content $hosts | Where-Object { $_ -notmatch 'vortex.data.microsoft.com' -and $_ -notmatch 'settings-win.data.microsoft.com' -and $_ -notmatch 'telemetry.microsoft.com' -and $_ -notmatch 'watson.telemetry.microsoft.com' -and $_ -notmatch 'diagnostics.support.microsoft.com' }
                Set-Content $hosts -Value $content
            }
            # 2. Enable DiagTrack
            Set-Service -Name DiagTrack -StartupType Automatic -ErrorAction SilentlyContinue
            Start-Service -Name DiagTrack -ErrorAction SilentlyContinue
            # 3. Enable Cortana & Bing search
            Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" -Name "CortanaConsent" -Value 1 -Force -ErrorAction SilentlyContinue
            Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Search" -Name "BingSearchEnabled" -Value 1 -Force -ErrorAction SilentlyContinue
            """
            subprocess.run(["powershell", "-Command", restore_commands], capture_output=True, text=True, errors="ignore")
            
        return {"success": True, "status": check_telemetry_status()}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/privacy/dns-servers")
def get_dns_servers_api():
    try:
        res = subprocess.run(
            ["powershell", "-Command", "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | Select-Object -ExpandProperty ServerAddresses"],
            capture_output=True, text=True, errors="ignore"
        )
        servers = list(set([s.strip() for s in res.stdout.splitlines() if s.strip()]))
        return {"success": True, "dns_servers": servers}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/privacy/ports")
def get_listening_ports_api():
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="ignore")
        lines = result.stdout.splitlines()
        ports = []
        pid_cache = {}
        
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 4:
                proto = parts[0].upper()
                if proto not in ["TCP", "UDP"]:
                    continue
                    
                local_addr = parts[1]
                
                if proto == "TCP":
                    state = parts[3].upper()
                    if "LISTENING" not in state and "ABHÖREN" not in state:
                        continue
                    pid = parts[4] if len(parts) >= 5 else parts[3]
                else:
                    pid = parts[3]
                    state = "LISTENING"
                
                port_match = re.search(r"[:\]](\d+)$", local_addr)
                if not port_match:
                    continue
                port = int(port_match.group(1))
                
                # Exclude standard high localhost ports to keep noise low, or keep them all. Let's keep all but resolve process names
                proc_name = pid_cache.get(pid)
                if not proc_name:
                    if pid == "0" or pid == "4":
                        proc_name = "System"
                    else:
                        try:
                            res_proc = subprocess.run(
                                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                capture_output=True, text=True, errors="ignore"
                            )
                            proc_parts = res_proc.stdout.strip().split(",")
                            if len(proc_parts) > 0:
                                proc_name = proc_parts[0].replace('"', '').strip()
                            else:
                                proc_name = "System / Service"
                        except Exception:
                            proc_name = "System / Service"
                    pid_cache[pid] = proc_name
                
                # Filter duplicate port representations
                if not any(p["port"] == port and p["protocol"] == proto for p in ports):
                    ports.append({
                        "protocol": proto,
                        "local_address": local_addr,
                        "port": port,
                        "pid": pid,
                        "process_name": proc_name if proc_name else "Unbekannt"
                    })
                    
        return {"success": True, "ports": sorted(ports, key=lambda x: x["port"])}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── VOICE PRIVACY ENGINE & REAL-TIME AUDIO MORPHER ─────────────────────────
import threading
import queue

def shift_pitch_and_formants(signal, pitch_factor, formant_factor, eq_bass=1.0, eq_mid=1.0, eq_treble=1.0, whisper_mode=False):
    import numpy as np
    n = len(signal)
    spec = np.fft.rfft(signal)
    
    mag = np.abs(spec)
    phase = np.angle(spec)
    
    # 1. Apply Frequency Domain Equalizer
    # Bass: < 250 Hz, Mid: 250 - 4000 Hz, Treble: > 4000 Hz
    freqs = np.fft.rfftfreq(n, d=1.0/16000)
    for i, f in enumerate(freqs):
        if f < 250:
            mag[i] *= eq_bass
        elif f < 4000:
            mag[i] *= eq_mid
        else:
            mag[i] *= eq_treble
            
    # 2. Estimate spectral envelope using cepstral liftering
    log_mag = np.log(mag + 1e-10)
    cepstrum = np.fft.irfft(log_mag)
    
    lifter_cutoff = int(n * 0.05)
    if lifter_cutoff < 5: 
        lifter_cutoff = 5
        
    cepstrum_env = cepstrum.copy()
    cepstrum_env[lifter_cutoff:-lifter_cutoff] = 0.0
    
    log_env = np.fft.rfft(cepstrum_env)
    log_env = log_env[:len(mag)]
    env = np.exp(log_env)
    
    if whisper_mode:
        # Replace excitation with random noise for whisper synthesis
        excitation = np.random.normal(0.0, 1.0, len(mag))
    else:
        # Flatten spectrum (excitation)
        excitation = mag / (env + 1e-10)
        
        # Linear interpolation for pitch shifting the excitation
        x_indices = np.arange(len(excitation))
        shifted_indices = x_indices / pitch_factor
        excitation = np.interp(shifted_indices, x_indices, excitation)
            
    # Linear interpolation for formant shifting the envelope
    env_indices = np.arange(len(env))
    shifted_env_indices = env_indices / formant_factor
    new_env = np.interp(shifted_env_indices, env_indices, env)
            
    # Reconstruct magnitude spectrum
    new_mag = excitation * new_env
    
    if whisper_mode:
        # Whisper uses randomized phase
        random_phase = np.random.uniform(-np.pi, np.pi, len(phase))
        new_spec = new_mag * np.exp(1j * random_phase)
    else:
        new_spec = new_mag * np.exp(1j * phase)
    
    # Inverse FFT
    new_signal = np.fft.irfft(new_spec)
    return new_signal

class VoiceChanger:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.rate = 16000
        self.chunk = 2048
        self.hop = 1024
        
        # Core parameters
        self.pitch_factor = 1.0
        self.formant_factor = 1.0
        
        # Noise Gate & EQ
        self.gate_threshold = -50.0  # in dB
        self.eq_bass = 1.0
        self.eq_mid = 1.0
        self.eq_treble = 1.0
        
        # Vibrato
        self.vibrato_freq = 5.0      # Hz
        self.vibrato_amp = 0.0       # Depth (0.0 = off)
        self.samples_processed = 0
        
        # Basic enhancements
        self.whisper_mode = False
        self.agc_enabled = True
        self.limiter_enabled = True
        
        # Device indexes
        self.input_device_idx = None
        self.output_device_idx = None
        self.monitor_device_idx = None
        
        # Self-monitoring
        self.hear_self = False
        self.self_delay_ms = 0
        
        # Visualizer telemetry
        self.current_rms = 0.0
        self.current_db = -100.0
        
        self.delay_queue = queue.Queue()
        
    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.samples_processed = 0
        self.thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
            
    def _audio_loop(self):
        import pyaudio
        import numpy as np
        p = pyaudio.PyAudio()
        
        try:
            in_stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                input=True,
                input_device_index=self.input_device_idx,
                frames_per_buffer=self.hop
            )
        except Exception as e:
            print(f"Failed to open input: {e}")
            p.terminate()
            self.is_running = False
            return
            
        try:
            out_stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                output=True,
                output_device_index=self.output_device_idx,
                frames_per_buffer=self.hop
            )
        except Exception as e:
            print(f"Failed to open output: {e}")
            in_stream.close()
            p.terminate()
            self.is_running = False
            return

        monitor_stream = None
        if self.hear_self and self.monitor_device_idx is not None:
            try:
                monitor_stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.rate,
                    output=True,
                    output_device_index=self.monitor_device_idx,
                    frames_per_buffer=self.hop
                )
            except Exception as e:
                print(f"Failed to open monitor stream: {e}")

        input_buffer = np.zeros(self.chunk, dtype=np.float32)
        output_buffer = np.zeros(self.chunk, dtype=np.float32)
        window = np.hanning(self.chunk)
        
        while self.is_running:
            try:
                data = in_stream.read(self.hop, exception_on_overflow=False)
                if not data:
                    continue
                in_samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                
                # Measure volume
                rms = np.sqrt(np.mean(in_samples**2)) if len(in_samples) > 0 else 0.0
                db = 20 * np.log10(rms + 1e-5)
                self.current_rms = float(rms)
                self.current_db = float(db)
                
                # Noise Gate
                if db < self.gate_threshold:
                    out_samples = np.zeros(self.hop, dtype=np.int16)
                    out_bytes = out_samples.tobytes()
                    out_stream.write(out_bytes)
                    if self.hear_self and monitor_stream:
                        self.delay_queue.put(out_bytes)
                        delay_hops = int(self.self_delay_ms / 64.0)
                        while self.delay_queue.qsize() > max(1, delay_hops):
                            delayed_bytes = self.delay_queue.get()
                            monitor_stream.write(delayed_bytes)
                    continue
                
                input_buffer[:-self.hop] = input_buffer[self.hop:]
                input_buffer[-self.hop:] = in_samples
                
                windowed_input = input_buffer * window
                
                # Vibrato Pitch LFO
                if self.vibrato_amp > 0 and not self.whisper_mode:
                    t = self.samples_processed / self.rate
                    pitch_mod = self.pitch_factor + self.vibrato_amp * np.sin(2 * np.pi * self.vibrato_freq * t)
                    self.samples_processed += self.hop
                else:
                    pitch_mod = self.pitch_factor
                
                processed = shift_pitch_and_formants(
                    windowed_input, 
                    pitch_mod, 
                    self.formant_factor,
                    eq_bass=self.eq_bass,
                    eq_mid=self.eq_mid,
                    eq_treble=self.eq_treble,
                    whisper_mode=self.whisper_mode
                )
                
                output_buffer += processed
                out_samples = output_buffer[:self.hop]
                
                output_buffer[:-self.hop] = output_buffer[self.hop:]
                output_buffer[-self.hop:] = 0.0
                
                # Apply AGC (Automatic Gain Control)
                if self.agc_enabled:
                    peak = np.max(np.abs(out_samples))
                    if 0.005 < peak < 0.6:
                        out_samples = out_samples * (0.7 / peak)
                
                # Apply Brickwall Peak Limiter (prevents clipping)
                if self.limiter_enabled:
                    peak = np.max(np.abs(out_samples))
                    if peak > 0.95:
                        out_samples = out_samples * (0.95 / peak)
                
                out_samples = np.clip(out_samples * 32767.0, -32768.0, 32767.0).astype(np.int16)
                out_bytes = out_samples.tobytes()
                
                out_stream.write(out_bytes)
                
                # Self-monitoring
                if self.hear_self and monitor_stream:
                    delay_hops = int(self.self_delay_ms / 64.0)
                    self.delay_queue.put(out_bytes)
                    while self.delay_queue.qsize() > max(1, delay_hops):
                        delayed_bytes = self.delay_queue.get()
                        monitor_stream.write(delayed_bytes)
                else:
                    while not self.delay_queue.empty():
                        self.delay_queue.get()
            except Exception as e:
                print(f"Audio loop exception: {e}")
                break
                
        try:
            in_stream.stop_stream()
            in_stream.close()
        except Exception:
            pass
        try:
            out_stream.stop_stream()
            out_stream.close()
        except Exception:
            pass
        if monitor_stream:
            try:
                monitor_stream.stop_stream()
                monitor_stream.close()
            except Exception:
                pass
        p.terminate()

voice_changer = VoiceChanger()

@app.get("/api/audio/voice/devices")
def get_voice_devices():
    import pyaudio
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    inputs = []
    outputs = []
    
    for i in range(0, numdevices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        device_name = device_info.get('name')
        
        try:
            device_name = device_name.encode('utf-8').decode('utf-8')
        except Exception:
            try:
                device_name = device_name.decode('cp1252')
            except Exception:
                pass
                
        device = {
            "index": i,
            "name": device_name,
            "max_input_channels": device_info.get('maxInputChannels'),
            "max_output_channels": device_info.get('maxOutputChannels')
        }
        
        if device_info.get('maxInputChannels') > 0:
            inputs.append(device)
        if device_info.get('maxOutputChannels') > 0:
            outputs.append(device)
            
    p.terminate()
    return {"success": True, "inputs": inputs, "outputs": outputs}

@app.post("/api/audio/voice/start")
async def start_voice(
    input_idx: int = Form(...),
    output_idx: int = Form(...),
    pitch: float = Form(1.0),
    formant: float = Form(1.0),
    gate: float = Form(-50.0),
    bass: float = Form(1.0),
    mid: float = Form(1.0),
    treble: float = Form(1.0),
    vibrato_freq: float = Form(5.0),
    vibrato_amp: float = Form(0.0),
    whisper: bool = Form(False),
    agc: bool = Form(True),
    limiter: bool = Form(True),
    hear_self: bool = Form(False),
    delay_ms: int = Form(0),
    monitor_idx: Optional[int] = Form(None)
):
    try:
        voice_changer.stop()
        
        voice_changer.input_device_idx = input_idx
        voice_changer.output_device_idx = output_idx
        voice_changer.pitch_factor = pitch
        voice_changer.formant_factor = formant
        voice_changer.gate_threshold = gate
        voice_changer.eq_bass = bass
        voice_changer.eq_mid = mid
        voice_changer.eq_treble = treble
        voice_changer.vibrato_freq = vibrato_freq
        voice_changer.vibrato_amp = vibrato_amp
        voice_changer.whisper_mode = whisper
        voice_changer.agc_enabled = agc
        voice_changer.limiter_enabled = limiter
        voice_changer.hear_self = hear_self
        voice_changer.self_delay_ms = delay_ms
        voice_changer.monitor_device_idx = monitor_idx
        
        voice_changer.start()
        return {"success": True, "status": "running"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audio/voice/stop")
def stop_voice_api():
    try:
        voice_changer.stop()
        voice_changer.current_rms = 0.0
        voice_changer.current_db = -100.0
        return {"success": True, "status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audio/voice/update")
def update_voice_api(
    pitch: float = Form(...),
    formant: float = Form(...),
    gate: float = Form(...),
    bass: float = Form(...),
    mid: float = Form(...),
    treble: float = Form(...),
    vibrato_freq: float = Form(...),
    vibrato_amp: float = Form(...),
    whisper: bool = Form(...),
    agc: bool = Form(...),
    limiter: bool = Form(...),
    hear_self: bool = Form(...),
    delay_ms: int = Form(...),
    monitor_idx: Optional[int] = Form(None)
):
    try:
        voice_changer.pitch_factor = pitch
        voice_changer.formant_factor = formant
        voice_changer.gate_threshold = gate
        voice_changer.eq_bass = bass
        voice_changer.eq_mid = mid
        voice_changer.eq_treble = treble
        voice_changer.vibrato_freq = vibrato_freq
        voice_changer.vibrato_amp = vibrato_amp
        voice_changer.whisper_mode = whisper
        voice_changer.agc_enabled = agc
        voice_changer.limiter_enabled = limiter
        
        was_hearing = voice_changer.hear_self
        voice_changer.hear_self = hear_self
        voice_changer.self_delay_ms = delay_ms
        voice_changer.monitor_device_idx = monitor_idx
        
        if voice_changer.is_running and hear_self and not was_hearing:
            voice_changer.stop()
            voice_changer.start()
            
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import WebSocket, WebSocketDisconnect
import asyncio

@app.websocket("/api/audio/voice/ws")
async def websocket_voice(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Send current audio levels and state at 30 fps
            await websocket.send_json({
                "rms": float(voice_changer.current_rms),
                "db": float(voice_changer.current_db),
                "gate_threshold": float(voice_changer.gate_threshold),
                "active": bool(voice_changer.is_running)
            })
            await asyncio.sleep(0.033)  # ~30 fps
    except WebSocketDisconnect:
        pass
    except Exception:
        pass

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=49152)
