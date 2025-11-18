#!/usr/bin/env python3
"""Teste rápido para verificar se YOLO está funcionando."""

import sys

try:
    from ultralytics import YOLO
    print("✅ YOLO (ultralytics) importado com sucesso")
except ImportError as e:
    print(f"❌ Erro ao importar YOLO: {e}")
    sys.exit(1)

try:
    print("Carregando modelo yolov8n.pt...")
    model = YOLO("yolov8n.pt")
    print("✅ Modelo YOLOv8 carregado com sucesso")
    print(f"   Info: {type(model)}")
except Exception as e:
    print(f"❌ Erro ao carregar modelo: {e}")
    sys.exit(1)

try:
    print("\nTestando detecção em imagem de exemplo...")
    if not __import__("pathlib").Path("exemplo.jpg").exists():
        print("   Baixando imagem de teste...")
        import requests
        r = requests.get("https://ultralytics.com/images/bus.jpg", timeout=30)
        r.raise_for_status()
        __import__("pathlib").Path("exemplo.jpg").write_bytes(r.content)
    
    results = model("exemplo.jpg", conf=0.25, classes=[0])  # classe 0 = person
    r = results[0]
    count = len(r.boxes) if r.boxes is not None else 0
    print(f"✅ Detecção funcionando! Pessoas detectadas: {count}")
except Exception as e:
    print(f"❌ Erro na detecção: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ YOLO está funcionando corretamente no projeto!")

