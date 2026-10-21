# tools/tool_canvas.py
"""
Frontier F: Obsidian Visual Canvas & Mind Map Generator.
Menghasilkan berkas .canvas resmi Obsidian secara otomatis dari topik,
rencana proyek, atau ide strategis, lengkap dengan kartu warna, alur panah,
dan tata letak hierarki yang rapi.
"""

import os
import sys
import json
import uuid
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import VAULT_PATH, MODEL_WRITER, OLLAMA_HOST
from core import vault_io
import requests


def _generate_id() -> str:
    """Buat ID unik 16 karakter heksadesimal untuk node/edge canvas."""
    return uuid.uuid4().hex[:16]


def _call_llm_for_canvas_structure(topic: str) -> Dict[str, Any]:
    """
    Meminta Ollama menstrukturkan topik ke dalam 4 tingkatan konsep:
    - goal: Visi utama
    - pillars: 2-3 pilar strategis
    - actions: 2 aksi taktis untuk setiap pilar
    - risks: 2 risiko & mitigasi
    """
    prompt = f"""Kamu adalah Visual Strategy Architect.
Rancanglah Mind Map & Roadmap Strategis terstruktur untuk topik berikut:
"{topic}"

KEMBALIKAN HANYA JSON MURNI DENGAN STRUKTUR BERIKUT (tanpa markdown pembuka/penutup):
{{
  "title": "Judul Singkat Strategi",
  "vision": "Deskripsi 1-2 kalimat visi atau tujuan akhir",
  "pillars": [
    {{
      "name": "Pilar 1: Nama Pilar",
      "desc": "Fokus utama pilar ini",
      "actions": [
        "Aksi taktis 1.1",
        "Aksi taktis 1.2"
      ]
    }},
    {{
      "name": "Pilar 2: Nama Pilar",
      "desc": "Fokus utama pilar ini",
      "actions": [
        "Aksi taktis 2.1",
        "Aksi taktis 2.2"
      ]
    }}
  ],
  "metrics": [
    "Indikator Sukses 1",
    "Indikator Sukses 2"
  ],
  "risks": [
    "Risiko utama & cara mitigasinya"
  ]
}}
"""
    try:
        payload = {
            "model": MODEL_WRITER,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2}
        }
        resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60)
        if resp.status_code == 200:
            text = resp.json().get("response", "").strip()
            # Bersihkan blok code jika model menyertakan ```json
            if "```" in text:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
                if match:
                    text = match.group(1).strip()
            data = json.loads(text)
            return data
    except Exception as e:
        print(f"[Canvas LLM Warning] Menggunakan generator heuristik fallback: {e}")

    # Fallback heuristik cerdas jika Ollama timeout atau non-JSON
    clean_topic = topic.strip().title()
    return {
        "title": clean_topic,
        "vision": f"Mencapai keunggulan dan eksekusi paripurna untuk strategi: {topic}.",
        "pillars": [
            {
                "name": "Pilar Fondasi & Riset",
                "desc": "Pemetaan kebutuhan inti, analisis data, dan persiapan arsitektur.",
                "actions": ["Audit kondisi awal dan pemetaan referensi", "Definisi SOP dan standar kualitas"]
            },
            {
                "name": "Pilar Eksekusi & Implementasi",
                "desc": "Pembangunan bertahap dan pengujian berkelanjutan.",
                "actions": ["Peluncuran prototipe tahap pertama", "Iterasi fitur inti berbasis umpan balik"]
            },
            {
                "name": "Pilar Skala & Keberlanjutan",
                "desc": "Otomasi sistem, evaluasi performa, dan dokumentasi jangka panjang.",
                "actions": ["Implementasi otomasi pemantauan", "Kompilasi laporan dan evaluasi berkala"]
            }
        ],
        "metrics": ["Tingkat penyelesaian target 100%", "Stabilitas sistem dan zero downtime"],
        "risks": ["Kurangnya konsistensi eksekusi (Mitigasi: Buat jadwal harian ketat)"]
    }


def build_canvas_data(structure: Dict[str, Any]) -> Dict[str, Any]:
    """
    Menghitung koordinat x, y, warna, dan menghubungkan edge antar node
    sesuai standar Obsidian Canvas (.canvas).
    
    Palet Warna Obsidian Canvas:
    - 1: Merah (Risiko/Peringatan)
    - 2: Oranye (Mitigasi/Perhatian)
    - 3: Kuning (Pilar Strategis)
    - 4: Hijau (Aksi Taktis / Sukses)
    - 5: Cyan (Metrik / Indikator)
    - 6: Ungu (Visi / Tujuan Inti)
    """
    nodes = []
    edges = []

    title = structure.get("title", "Strategi Proyek")
    vision = structure.get("vision", "Visi Utama")
    pillars = structure.get("pillars", [])
    metrics = structure.get("metrics", [])
    risks = structure.get("risks", [])

    # 1. Node Visi / Tujuan Pusat (Tier 0: Top Center)
    root_id = _generate_id()
    root_node = {
        "id": root_id,
        "type": "text",
        "text": f"## 🎯 {title}\n\n**Visi Strategis:**\n{vision}",
        "x": 0,
        "y": 0,
        "width": 420,
        "height": 180,
        "color": "6"  # Ungu
    }
    nodes.append(root_node)

    # 2. Node Pilar (Tier 1: y = 300)
    pillar_count = len(pillars)
    pillar_spacing = 420
    start_x = -((pillar_count - 1) * pillar_spacing) / 2

    for i, pillar in enumerate(pillars):
        p_x = int(start_x + (i * pillar_spacing))
        p_y = 300
        p_id = _generate_id()
        p_name = pillar.get("name", f"Pilar {i+1}")
        p_desc = pillar.get("desc", "")
        
        p_node = {
            "id": p_id,
            "type": "text",
            "text": f"### 🏛️ {p_name}\n\n{p_desc}",
            "x": p_x,
            "y": p_y,
            "width": 360,
            "height": 160,
            "color": "3"  # Kuning
        }
        nodes.append(p_node)

        # Hubungkan Root -> Pilar
        edges.append({
            "id": _generate_id(),
            "fromNode": root_id,
            "fromSide": "bottom",
            "toNode": p_id,
            "toSide": "top",
            "label": "Pilar Utama"
        })

        # 3. Node Aksi Taktis di bawah setiap pilar (Tier 2: y = 560 & y = 740)
        actions = pillar.get("actions", [])
        for j, action in enumerate(actions):
            a_id = _generate_id()
            a_y = 560 + (j * 170)
            a_node = {
                "id": a_id,
                "type": "text",
                "text": f"#### ✅ Aksi {i+1}.{j+1}\n\n- [ ] {action}",
                "x": p_x,
                "y": a_y,
                "width": 360,
                "height": 130,
                "color": "4"  # Hijau
            }
            nodes.append(a_node)

            # Hubungkan Pilar -> Aksi
            edges.append({
                "id": _generate_id(),
                "fromNode": p_id if j == 0 else nodes[-2]["id"],
                "fromSide": "bottom",
                "toNode": a_id,
                "toSide": "top",
                "label": "Eksekusi"
            })

    # 4. Node Metrik & Risiko di samping (Tier Metrik: Kiri, Tier Risiko: Kanan)
    if metrics:
        m_id = _generate_id()
        m_text = "### 📊 Indikator Keberhasilan (KPI)\n\n" + "\n".join([f"- ⭐ {m}" for m in metrics])
        nodes.append({
            "id": m_id,
            "type": "text",
            "text": m_text,
            "x": int(start_x - 420),
            "y": 100,
            "width": 340,
            "height": 220,
            "color": "5"  # Cyan
        })
        edges.append({
            "id": _generate_id(),
            "fromNode": root_id,
            "fromSide": "left",
            "toNode": m_id,
            "toSide": "right",
            "label": "Target KPI"
        })

    if risks:
        r_id = _generate_id()
        r_text = "### ⚠️ Analisis Risiko & Mitigasi\n\n" + "\n".join([f"- 🛡️ {r}" for r in risks])
        nodes.append({
            "id": r_id,
            "type": "text",
            "text": r_text,
            "x": int(-start_x + 420) if start_x != 0 else 460,
            "y": 100,
            "width": 340,
            "height": 220,
            "color": "1"  # Merah
        })
        edges.append({
            "id": _generate_id(),
            "fromNode": root_id,
            "fromSide": "right",
            "toNode": r_id,
            "toSide": "left",
            "label": "Manajemen Risiko"
        })

    return {"nodes": nodes, "edges": edges}


def generate_canvas(topic: str, folder_target: str = "01-Projects") -> Dict[str, Any]:
    """
    Eksekutor utama: Mengonversi topik menjadi file .canvas di Obsidian Vault.
    """
    clean_topic = topic.strip()
    if not clean_topic:
        return {"success": False, "error": "Topik canvas tidak boleh kosong."}

    # 1. Buat struktur pemikiran via LLM / Heuristik
    structure = _call_llm_for_canvas_structure(clean_topic)

    # 2. Bangun koordinat nodes dan edges Obsidian Canvas
    canvas_dict = build_canvas_data(structure)

    # 3. Sanitasi nama berkas
    safe_name = re.sub(r'[\\/*?:"<>|]', '', structure.get("title", clean_topic))
    safe_name = re.sub(r'\s+', ' ', safe_name).strip()[:50]
    filename = f"Canvas - {safe_name}.canvas"

    vault = Path(VAULT_PATH)
    target_dir = vault / folder_target
    target_dir.mkdir(parents=True, exist_ok=True)
    canvas_file_path = target_dir / filename

    # 4. Tulis ke disk
    try:
        vault_io.atomic_write(canvas_file_path, json.dumps(canvas_dict, indent=2, ensure_ascii=False))

        node_count = len(canvas_dict.get("nodes", []))
        edge_count = len(canvas_dict.get("edges", []))

        msg = (
            f"🎨 **Visual Canvas Berhasil Dibuat!**\n\n"
            f"- **Berkas:** `[[{canvas_file_path.name}]]`\n"
            f"- **Lokasi:** `{folder_target}/{canvas_file_path.name}`\n"
            f"- **Jumlah Kartu (Nodes):** {node_count} kartu visual berwarna\n"
            f"- **Jumlah Alur (Edges):** {edge_count} koneksi relasi\n\n"
            f"*Buka berkas di Obsidian untuk menggeser, memperbesar, atau menambahkan ide visual Anda.*"
        )
        return {
            "success": True,
            "message": msg,
            "file_path": str(canvas_file_path),
            "filename": canvas_file_path.name,
            "nodes": node_count,
            "edges": edge_count
        }
    except Exception as e:
        return {"success": False, "error": f"Gagal menulis file .canvas: {str(e)}"}


def run_canvas_command(topic: str) -> str:
    """Wrapper untuk dieksekusi via slash command /canvas <topik>."""
    if not topic.strip():
        return "❌ Format perintah: `/canvas <topik atau rencana proyek>` (contoh: `/canvas Rencana Ekspansi Bisnis 2026`)"
    res = generate_canvas(topic)
    if res["success"]:
        return res["message"]
    return f"❌ {res.get('error', 'Terjadi kesalahan saat membuat canvas')}"


if __name__ == "__main__":
    print("Menguji Obsidian Visual Canvas Generator...")
    res = generate_canvas("Rencana Strategis AI Cognitive OS 2026")
    print(res["message"])

