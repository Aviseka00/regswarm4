"""Windows DPAPI-protected provider credentials; environment variables override."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "provider_credentials.json"


class Blob(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def crypt(payload, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Use environment variables for provider keys on this operating system")
    buffer = ctypes.create_string_buffer(payload)
    source = Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    method = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    method.restype = wintypes.BOOL
    second = None if decrypt else "RegSwarm provider key"
    if not method(ctypes.byref(source), second, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError(f"Windows credential encryption failed (system code {ctypes.windll.kernel32.GetLastError()})")
    try:
        return ctypes.string_at(output.data, output.length)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def save(provider, key):
    if provider not in ("groq", "anthropic") or not isinstance(key, str) or not key.strip():
        raise ValueError("Valid provider and key required")
    values = json.loads(PATH.read_text()) if PATH.exists() else {}
    values[provider] = base64.b64encode(crypt(key.strip().encode())).decode()
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(values), encoding="utf-8")
    temporary.replace(PATH)


def get(provider):
    env = {"groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
    if os.environ.get(env):
        return os.environ[env]
    if PATH.exists():
        values = json.loads(PATH.read_text(encoding="utf-8"))
        if values.get(provider):
            return crypt(base64.b64decode(values[provider]), decrypt=True).decode()
    return None


if __name__ == "__main__":
    import sys
    request = json.load(sys.stdin)
    save(request["provider"], request["key"])
    print("Provider credential saved with Windows encryption.")
