#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Marcar pessoas em imagens usando YOLO (Ultralytics).

- Detecta todas as pessoas (classe COCO "person").
- Gera imagem anotada com caixas e, quando disponível, máscaras (contornos).
- Exporta metadata em JSON (e opcionalmente CSV).

Requisitos:
    pip install ultralytics opencv-python pillow numpy

Exemplos:
    python marcar_pessoas.py --input exemplo.jpg
    python marcar_pessoas.py --input exemplo.jpg --mode bbox --conf 0.35 --no-label
    python marcar_pessoas.py --input exemplo.jpg --output_dir out --device cuda:0

Autor: (você)
"""

import argparse
import os
import sys
import json
import csv
import hashlib
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
import cv2
from PIL import Image, ImageOps
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json


# Checagem amigável para ultralytics
try:
    from ultralytics import YOLO
except Exception as exc:
    print(
        "Erro ao importar 'ultralytics'. Instale com:\n"
        "    pip install ultralytics\n"
        f"Detalhes: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_image_fix_exif(image_path: Path) -> np.ndarray:
    """
    Lê a imagem corrigindo rotação EXIF e retornando como array BGR (OpenCV).
    """
    img = Image.open(str(image_path))
    img = ImageOps.exif_transpose(img).convert("RGB")  # corrige orientação
    arr = np.array(img)  # RGB
    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)  # para BGR (OpenCV)
    return arr


def _auto_device_hint(device_arg: Optional[str]) -> str:
    """
    Determina o device a utilizar. Se não fornecido, tenta GPU e cai para CPU.
    """
    if device_arg:
        return device_arg
    # Heurística simples: se CUDA disponível no PyTorch usado pelo ultralytics, ele usa "cuda".
    # Caso contrário, CPU.
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _color_from_index(idx: int) -> Tuple[int, int, int]:
    """
    Gera uma cor BGR estável a partir de um índice.
    """
    # Paleta determinística simples via hashing
    rng = np.random.default_rng(seed=idx + 12345)
    c = rng.integers(0, 255, size=3).tolist()
    return int(c[2]), int(c[1]), int(c[0])  # B, G, R


def _draw_mask_overlay(
    base_img: np.ndarray,
    polygons: List[np.ndarray],
    color: Tuple[int, int, int],
    alpha: float = 0.25,
    thickness: int = 3,
) -> None:
    """
    Desenha contornos e um leve preenchimento transparente para os polígonos da máscara.
    """
    overlay = base_img.copy()
    for pts in polygons:
        if pts.shape[0] < 3:
            continue
        pts_i32 = pts.astype(np.int32)
        cv2.fillPoly(overlay, [pts_i32], color)
        cv2.polylines(base_img, [pts_i32], isClosed=True, color=color, thickness=thickness, lineType=cv2.LINE_AA)
    # aplica transparência
    cv2.addWeighted(overlay, alpha, base_img, 1 - alpha, 0, dst=base_img)


def _draw_bbox(
    img: np.ndarray,
    box: Tuple[int, int, int, int],
    color: Tuple[int, int, int],
    label: Optional[str],
    thickness: int = 3,
) -> None:
    x1, y1, x2, y2 = map(int, box)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    if label:
        # fundo do rótulo
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        ty = max(0, y1 - th - 6)
        cv2.rectangle(img, (x1, ty), (x1 + tw + 8, ty + th + 6), color, -1)
        cv2.putText(
            img,
            label,
            (x1 + 4, ty + th + 1),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


def _draw_total_count(
    img: np.ndarray,
    total: int,
    position: str = "top_left",
    alpha: float = 0.4,
    pad: int = 10,
):
    """
    Desenha um rótulo com o total de pessoas na imagem anotada.

    position: "top_left", "top_right", "bottom_left", "bottom_right"
    """
    label = f"Total de pessoas: {total}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.9
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)

    h, w = img.shape[:2]
    if position == "top_left":
        x, y = 12, 12
    elif position == "top_right":
        x, y = w - (tw + 2 * pad) - 12, 12
    elif position == "bottom_left":
        x, y = 12, h - (th + 2 * pad) - 12
    else:  # bottom_right
        x, y = w - (tw + 2 * pad) - 12, h - (th + 2 * pad) - 12

    # Fundo semitransparente
    overlay = img.copy()
    cv2.rectangle(
        overlay,
        (x, y),
        (x + tw + 2 * pad, y + th + 2 * pad),
        (0, 0, 0),
        -1,
    )
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, dst=img)

    # Texto em branco
    cv2.putText(
        img,
        label,
        (x + pad, y + th + pad - 2),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def marcar_pessoas(
    input_image: Path,
    output_dir: Optional[Path] = None,
    mode: str = "seg",
    conf: float = 0.25,
    thickness: int = 3,
    show_label: bool = True,
    device: Optional[str] = None,
    export_csv: bool = True,
) -> Dict[str, Any]:
    """
    Processa a imagem, detecta pessoas e escreve resultado anotado.

    Retorna um dicionário com:
        {
            "count": int,
            "output_image": str,
            "json_path": str,
            "csv_path": Optional[str],
            "detections": [
                {
                    "id": int,
                    "score": float,
                    "bbox": [x1, y1, x2, y2],
                    "polygons": [ [[x,y], ...], ... ]  # quando seg
                },
                ...
            ]
        }
    """
    assert input_image.exists(), f"Arquivo não encontrado: {input_image}"
    if output_dir is None:
        output_dir = input_image.parent
    _ensure_dir(output_dir)

    device = _auto_device_hint(device)

    # Modelo: segmentação se possível
    mode = mode.lower().strip()
    if mode not in {"seg", "bbox"}:
        raise ValueError("Parâmetro --mode deve ser 'seg' ou 'bbox'.")

    model_name = "yolov8n-seg.pt" if mode == "seg" else "yolov8n.pt"
    model = YOLO(model_name)

    # Leitura e correção de EXIF
    img_bgr = _read_image_fix_exif(input_image)

    # Inferência restringindo à classe 0 (person)
    # Nota: Ultralytics faz NMS internamente.
    results = model(img_bgr, conf=conf, device=device, classes=[0])
    r = results[0]  # processamos uma imagem

    detections = []
    count = 0

    # Coleta de caixas e máscaras
    boxes_xyxy = r.boxes.xyxy.cpu().numpy() if r.boxes is not None else np.zeros((0, 4))
    scores = r.boxes.conf.cpu().numpy().tolist() if r.boxes is not None and r.boxes.conf is not None else []
    masks_polys: List[List[np.ndarray]] = []

    if mode == "seg" and r.masks is not None:
        # r.masks.xy é uma lista de listas de polígonos (cada máscara pode ter 1+ segmentos)
        # Em versões recentes, usar r.masks.xyn (normalizado) ou r.masks.xy (em pixels).
        # Preferimos r.masks.xy (coordenadas já na escala original).
        # Atenção: alguns retornos podem ser List[np.ndarray] (um segmento por mask).
        raw = r.masks.xy
        if raw is None:
            # fallback: não disponível -> opera como bbox
            masks_polys = [[] for _ in range(len(boxes_xyxy))]
        else:
            # Padroniza: cada máscara vira uma lista de np.ndarrays (segmentos)
            masks_polys = []
            for seg in raw:
                if isinstance(seg, np.ndarray):
                    masks_polys.append([seg])
                elif isinstance(seg, list):
                    # pode ser lista de segmentos
                    segs = []
                    for s in seg:
                        segs.append(np.array(s))
                    masks_polys.append(segs)
                else:
                    masks_polys.append([])
    else:
        masks_polys = [[] for _ in range(len(boxes_xyxy))]

    # Desenho
    annotated = img_bgr.copy()
    for i, box in enumerate(boxes_xyxy):
        count += 1
        color = _color_from_index(i)
        label = f"Pessoa #{count} ({scores[i]:.2f})" if show_label and i < len(scores) else (f"Pessoa #{count}" if show_label else None)

        # Caixas sempre (mesmo no modo seg)
        _draw_bbox(annotated, (int(box[0]), int(box[1]), int(box[2]), int(box[3])), color, label, thickness)

        # Máscaras (contornos) se houver
        if mode == "seg" and i < len(masks_polys) and masks_polys[i]:
            _draw_mask_overlay(annotated, masks_polys[i], color=color, alpha=0.25, thickness=thickness)

        det: Dict[str, Any] = {
            "id": count,
            "score": float(scores[i]) if i < len(scores) else None,
            "bbox": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
        }
        if mode == "seg":
            # Serializa polígonos
            polys_serializable = []
            for seg in masks_polys[i]:
                polys_serializable.append([[float(x), float(y)] for x, y in seg])
            det["polygons"] = polys_serializable

        detections.append(det)

    # Desenha total de pessoas na imagem
    _draw_total_count(annotated, count, position="top_left", alpha=0.4, pad=10)

    # Saídas
    stem = input_image.stem
    ext = input_image.suffix.lower()
    out_image_path = output_dir / f"{stem}_marked{ext if ext in ('.jpg', '.jpeg', '.png') else '.jpg'}"
    json_path = output_dir / f"{stem}_marked_meta.json"
    csv_path = output_dir / f"{stem}_marked_boxes.csv"

    # Escreve imagem anotada (garante formato suportado)
    ok = cv2.imwrite(str(out_image_path), annotated)
    if not ok:
        # fallback para .png
        out_image_path = output_dir / f"{stem}_marked.png"
        cv2.imwrite(str(out_image_path), annotated)

    # JSON
    meta = {
        "input": str(input_image),
        "output_image": str(out_image_path),
        "mode": mode,
        "confidence_threshold": conf,
        "device": device,
        "count": count,
        "detections": detections,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # CSV (opcional)
    if export_csv:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            header = ["id", "score", "x1", "y1", "x2", "y2"]
            writer.writerow(header)
            for d in detections:
                row = [d["id"], d.get("score", None)] + d["bbox"]
                writer.writerow(row)
        csv_out = str(csv_path)
    else:
        csv_out = None

    return {
        "count": count,
        "output_image": str(out_image_path),
        "json_path": str(json_path),
        "csv_path": csv_out,
        "detections": detections,
    }


def _db_connect_from_env():
    """
    Cria conexão com Postgres usando variáveis de ambiente.
    Requer: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    Retorna conexão ou None se não configurado ou sem psycopg2.
    """
    if psycopg2 is None:
        return None
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    pwd = os.getenv("DB_PASSWORD")
    if not all([host, name, user, pwd]):
        return None
    sslmode = os.getenv("DB_SSLMODE")  # opcional
    conn_kwargs = dict(host=host, port=port, dbname=name, user=user, password=pwd)
    if sslmode:
        conn_kwargs["sslmode"] = sslmode
    try:
        conn = psycopg2.connect(**conn_kwargs)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Aviso: não foi possível conectar ao DB: {e}", file=sys.stderr)
        return None


def _db_ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                input_filename TEXT,
                output_filename TEXT,
                metadata JSONB,
                input_image BYTEA,
                output_image BYTEA,
                hash TEXT UNIQUE
            );
            """
        )
        # Se a tabela já existia sem a coluna hash, garante a coluna e índice único compatível com ON CONFLICT (hash)
        cur.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS hash TEXT;")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS images_hash_key ON images(hash);")
        # Ensure a named UNIQUE constraint exists so ON CONFLICT (hash) will always match
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'images_hash_unique'
                ) THEN
                    ALTER TABLE images ADD CONSTRAINT images_hash_unique UNIQUE (hash);
                END IF;
            END$$;
            """
        )


def _db_store_result(conn, input_path: Path, result: Dict[str, Any]) -> Optional[int]:
    """
    Armazena a imagem de entrada, a imagem anotada e o JSON no Postgres.
    Retorna o id inserido.
    """
    try:
        with open(input_path, "rb") as f:
            input_bytes = f.read()
        with open(result["output_image"], "rb") as f:
            output_bytes = f.read()
    except Exception as e:
        print(f"Aviso: falha ao ler arquivos de imagem para armazenamento: {e}", file=sys.stderr)
        return None

    # Hash para deduplicação
    img_hash = hashlib.sha256(input_bytes).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                INSERT INTO images (input_filename, output_filename, metadata, input_image, output_image, hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (hash) DO NOTHING
                RETURNING id;
                """
            ),
            [
                str(input_path.name),
                Path(result["output_image"]).name,
                Json({k: v for k, v in result.items() if k != "detections"}),
                psycopg2.Binary(input_bytes),
                psycopg2.Binary(output_bytes),
                img_hash,
            ],
        )
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
        # Caso já exista, retorna id existente
        cur.execute("SELECT id FROM images WHERE hash = %s LIMIT 1;", [img_hash])
        row = cur.fetchone()
        return int(row[0]) if row else None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Marcar todas as pessoas em uma imagem ou em todas as imagens de uma pasta.")
    p.add_argument(
        "--input",
        required=True,
        type=str,
        help="Caminho da imagem (jpg/png) ou de uma pasta contendo imagens.",
    )
    p.add_argument("--output_dir", type=str, default=None, help="Diretório de saída (padrão: pasta do input).")
    p.add_argument("--mode", type=str, default="seg", choices=["seg", "bbox"], help="Modo de anotação: 'seg' (contorno) ou 'bbox' (caixa).")
    p.add_argument("--conf", type=float, default=0.25, help="Confiança mínima para deteção.")
    p.add_argument("--thickness", type=int, default=3, help="Espessura de linhas para desenho.")
    p.add_argument("--label", dest="show_label", action="store_true", help="Exibir rótulos (índice/confiança). (padrão)")
    p.add_argument("--no-label", dest="show_label", action="store_false", help="Não exibir rótulos.")
    p.set_defaults(show_label=True)
    p.add_argument("--device", type=str, default=None, help='Device: "cpu", "cuda", "cuda:0", etc. (padrão: auto)')
    p.add_argument("--no-csv", dest="export_csv", action="store_false", help="Não exportar CSV com caixas.")
    p.set_defaults(export_csv=True)
    # Armazenamento em banco
    p.add_argument("--db-store", dest="db_store", action="store_true", help="Salvar resultados no banco (Postgres) se configurado via env.")
    p.add_argument("--no-db-store", dest="db_store", action="store_false", help="Não salvar no banco.")
    p.set_defaults(db_store=None)
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_dir_arg = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    # Decide se armazena no DB
    db_enabled_env = all([os.getenv("DB_HOST"), os.getenv("DB_NAME"), os.getenv("DB_USER"), os.getenv("DB_PASSWORD")])
    db_store = args.db_store if args.db_store is not None else db_enabled_env
    if db_store:
        print("Aviso: --Não foi possivel pegar as variaveis do .env")
    conn = _db_connect_from_env() if db_store else None
    if db_store and conn is None:
        print("Aviso: --db-store ativo, mas conexão com DB não disponível. Pulando armazenamento.", file=sys.stderr)
        db_store = False

    if input_path.is_dir():
        # Lista imagens de primeiro nível (sem recursão)
        exts = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
        images = [p for p in sorted(input_path.iterdir()) if p.suffix in exts and p.is_file()]
        if not images:
            print(f"Nenhuma imagem *.jpg/*.jpeg/*.png encontrada em: {input_path}", file=sys.stderr)
            sys.exit(1)

        # Define diretório de saída: se não for dado, cria subpasta 'out' dentro do input
        output_dir = output_dir_arg if output_dir_arg else (input_path / "out")
        _ensure_dir(output_dir)

        total_images = 0
        total_people = 0
        results_summary = []
        for img_path in images:
            try:
                r = marcar_pessoas(
                    input_image=img_path,
                    output_dir=output_dir,
                    mode=args.mode,
                    conf=args.conf,
                    thickness=args.thickness,
                    show_label=args.show_label,
                    device=args.device,
                    export_csv=args.export_csv,
                )
                total_images += 1
                total_people += int(r.get("count", 0))
                results_summary.append(r)
                db_id_info = ""
                if db_store and conn is not None:
                    try:
                        _db_ensure_table(conn)
                        row_id = _db_store_result(conn, img_path, r)
                        if row_id is not None:
                            db_id_info = f" | DB id={row_id}"
                    except Exception as db_e:
                        print(f"Aviso: falha ao salvar no DB: {db_e}", file=sys.stderr)
                print(f"OK: {img_path.name} -> {r['count']} pessoa(s) | {r['output_image']}{db_id_info}")
            except Exception as e:
                print(f"ERRO: {img_path.name} -> {e}", file=sys.stderr)

        print("\nResumo:")
        print(f"Imagens processadas: {total_images}")
        print(f"Total de pessoas detectadas (soma): {total_people}")
        print(f"Saídas em: {output_dir}")
    else:
        output_dir = output_dir_arg

        result = marcar_pessoas(
            input_image=input_path,
            output_dir=output_dir,
            mode=args.mode,
            conf=args.conf,
            thickness=args.thickness,
            show_label=args.show_label,
            device=args.device,
            export_csv=args.export_csv,
        )

        print(json.dumps({k: v for k, v in result.items() if k != "detections"}, ensure_ascii=False, indent=2))
        print(f"\nPessoas detectadas: {result['count']}")
        print(f"Imagem anotada: {result['output_image']}")
        print(f"Metadata JSON: {result['json_path']}")
        if result.get("csv_path"):
            print(f"CSV: {result['csv_path']}")
        if db_store and conn is not None:
            try:
                _db_ensure_table(conn)
                row_id = _db_store_result(conn, input_path, result)
                if row_id is not None:
                    print(f"Armazenado no DB com id={row_id}")
            except Exception as db_e:
                print(f"Aviso: falha ao salvar no DB: {db_e}", file=sys.stderr)


if __name__ == "__main__":
    main()
