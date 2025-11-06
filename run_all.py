import os
import sys
import time
import signal
import subprocess

try:
    import requests  # type: ignore
except Exception:
    print("Instale as dependências primeiro: pip install -r requirements.txt")
    sys.exit(1)


def wait_for_api(url: str, timeout_seconds: int = 60) -> bool:
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    env = os.environ.copy()
    env.setdefault("API_DEVICE", "cpu")

    # 1) Inicia API (uvicorn) usando o Python atual/da venv
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--workers",
        "1",
    ]
    api_proc = subprocess.Popen(api_cmd, env=env)

    # 2) Aguarda API subir
    ok = wait_for_api("http://127.0.0.1:8000/docs", timeout_seconds=90)
    if not ok:
        try:
            api_proc.terminate()
        finally:
            print("Falha ao iniciar a API em 127.0.0.1:8000")
            return 1

    # 3) Inicia Streamlit apontando para API
    env_streamlit = env.copy()
    env_streamlit["API_URL"] = "http://127.0.0.1:8000"
    ui_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "streamlit_app.py",
        "--server.address=127.0.0.1",
        "--server.port=8501",
    ]
    try:
        ui_proc = subprocess.Popen(ui_cmd, env=env_streamlit)
        ui_proc.wait()
        return_code = ui_proc.returncode or 0
    except KeyboardInterrupt:
        return_code = 0
    finally:
        # Tenta encerrar a API quando a UI fecha
        try:
            if api_proc.poll() is None:
                if os.name == "nt":
                    api_proc.send_signal(signal.CTRL_BREAK_EVENT)
                api_proc.terminate()
        except Exception:
            pass

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())


