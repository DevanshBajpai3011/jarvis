import platform
import psutil

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception:
    HAS_NVML = False


def get_system_body_specs() -> str:
    """
    Queries host hardware environment (CPU, GPU, RAM, Storage, OS)
    and returns a formatted text summary describing the system as J.A.R.V.I.S.'s physical body.
    """
    try:
        os_info = f"{platform.system()} {platform.release()} (build {platform.version()})"
    except Exception:
        os_info = "Windows"

    cpu_model = platform.processor() or "Multi-Core x86_64 Processor"
    cpu_cores = psutil.cpu_count(logical=False) or 0
    cpu_threads = psutil.cpu_count(logical=True) or 0
    cpu_info = f"{cpu_model} ({cpu_cores} cores / {cpu_threads} threads)"

    gpu_info = "Integrated Host Graphics"
    if HAS_NVML:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            name = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)
            vram_gb = pynvml.nvmlDeviceGetMemoryInfo(handle).total / (1024 ** 3)
            gpu_info = f"{name} ({vram_gb:.1f} GB VRAM)"
        except Exception:
            gpu_info = "NVIDIA Dedicated GPU"

    ram_total_gb = psutil.virtual_memory().total / (1024 ** 3)
    ram_info = f"{ram_total_gb:.1f} GB total RAM"

    try:
        disk_total_gb = psutil.disk_usage("/").total / (1024 ** 3)
        disk_info = f"{disk_total_gb:.1f} GB total storage"
    except Exception:
        disk_info = "Primary Solid State Drive"

    body_specs = (
        f"- Operating System: {os_info}\n"
        f"- Core Processor (CPU): {cpu_info}\n"
        f"- Neural/Graphics Processing Unit (GPU): {gpu_info}\n"
        f"- System Memory (RAM): {ram_info}\n"
        f"- Primary Mass Storage: {disk_info}"
    )
    return body_specs


if __name__ == "__main__":
    print("J.A.R.V.I.S. Host Physical Body Specs:")
    print(get_system_body_specs())
