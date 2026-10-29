"""Premier lancement (version Microsoft Store, ou toute installation sans les modeles vocaux) : une petite fenetre
telecharge les modeles de reconnaissance vocale, avec une barre de progression, avant que Hear demarre.

Sans cela, le premier chargement telechargeait sans rien montrer : on aurait pu croire que Hear ne marche pas.
La liste est la meme que celle de l'installateur (installateur/src/modeles.go).
Groupes : fast (Parakeet + VAD), lid (detection de langue), precise (Canary). Hear est complet avec fast + lid ;
precise est ajoute si c'est le modele choisi (c'est le choix par defaut).
"""
import shutil
import threading
import traceback
from pathlib import Path

import hear_config
from hear_config import log

MODELES = [
    ("fast", "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/config.json", "model/config.json", 97, "666903c76b9798caf2c210afd4f6cd60b08a8dbf9800ec8d7a3bc0d2148ac466"),
    ("fast", "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/decoder_joint-model.int8.onnx", "model/decoder_joint-model.int8.onnx", 18202004, "eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70"),
    ("fast", "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/encoder-model.int8.onnx", "model/encoder-model.int8.onnx", 652183999, "6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09"),
    ("fast", "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/vocab.txt", "model/vocab.txt", 93939, "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d"),
    ("fast", "https://huggingface.co/istupakov/silero-vad-onnx/resolve/main/silero_vad.onnx", "model/silero_vad.onnx", 2327524, "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"),
    ("lid", "https://huggingface.co/onnx-community/whisper-tiny/resolve/main/added_tokens.json", "model_lid/added_tokens.json", 34604, "9715fd2243b6f06a5858b5e32950d2853f73dd5bc201aafcf76f5082a2d8acd1"),
    ("lid", "https://huggingface.co/onnx-community/whisper-tiny/resolve/main/config.json", "model_lid/config.json", 2243, "46aeea0a406afbeb563fc8e59ca10609203df4299af6a83f73752fef369efd2d"),
    ("lid", "https://huggingface.co/onnx-community/whisper-tiny/resolve/main/vocab.json", "model_lid/vocab.json", 1036584, "50d6a919f0a0601d56a04eb583c780d18553aa388254ba3158eb6a00f13e2c1a"),
    ("lid", "https://huggingface.co/onnx-community/whisper-tiny/resolve/main/onnx/encoder_model.onnx", "model_lid/onnx/encoder_model.onnx", 32904992, "6642befb640f950d4a8cbbd17834d59e7e75f575b81ccf213e06b050623ab1dd"),
    ("lid", "https://huggingface.co/onnx-community/whisper-tiny/resolve/main/onnx/decoder_model_merged_int8.onnx", "model_lid/onnx/decoder_model_merged.onnx", 30719241, "25e807a962b6349356d0ea5d0dfe530b7e5bf0e2a484aeca0359d03143faddd3"),
    ("precise", "https://huggingface.co/istupakov/canary-1b-v2-onnx/resolve/main/config.json", "model_canary/config.json", 68, "f90ace8e35326dcd47c7330b230644fa0835083ed1e89e2f59aa08ba10d74f54"),
    ("precise", "https://huggingface.co/istupakov/canary-1b-v2-onnx/resolve/main/decoder-model.int8.onnx", "model_canary/decoder-model.int8.onnx", 170040374, "52d83aa7aad41fbbe4f9dfcd341d784735a6eb4c6eb0d3290fc27a0d8ac39abf"),
    ("precise", "https://huggingface.co/istupakov/canary-1b-v2-onnx/resolve/main/encoder-model.int8.onnx", "model_canary/encoder-model.int8.onnx", 859078138, "6d96e9945898e5ace48f4efecd459ca1df81859730be27b8af6b197639403ee1"),
    ("precise", "https://huggingface.co/istupakov/canary-1b-v2-onnx/resolve/main/vocab.txt", "model_canary/vocab.txt", 208022, "2c9efe6104fd29522ea27ce0e3aef5d37c690af4e5a4232e643e23ca403ffea3"),
]


MARGE_DISQUE = 500 * 1024 * 1024


def a_telecharger(groupes, dossier=None):
    """Les fichiers de ces groupes qui manquent (ou ont la mauvaise taille) dans le dossier des donnees."""
    dossier = dossier or hear_config.DONNEES
    manque = []
    for g, url, dest, taille, sha in MODELES:
        if g not in groupes:
            continue
        p = dossier / dest
        if not p.is_file() or p.stat().st_size != taille:
            manque.append((url, dest, taille, sha))
    return manque


def groupes_voulus(cfg):
    g = {"fast", "lid"}
    if cfg.get("model") == "canary":
        g.add("precise")
    return g


def necessaire(cfg, dossier=None):
    """Vrai si le modele de base (Fast) manque : sans lui Hear ne peut rien transcrire."""
    return bool(a_telecharger({"fast"}, dossier))


def espace_libre(chemin):
    """Place libre du disque qui recevra le dossier, meme si le dossier (ou son parent) n'existe pas encore."""
    p = Path(chemin)
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free


def _mo(n):
    return f"{n / 1048576:.0f} MB" if n < 1073741824 else f"{n / 1073741824:.1f} GB"


def telecharger_tout(manque, suivi, annule, dossier=None):
    """Telecharge chaque fichier (reprise, taille et empreinte verifiees). suivi(octets_faits, octets_total, nom)."""
    from hear_agent import telecharger
    dossier = dossier or hear_config.DONNEES
    total = sum(t for _, _, t, _ in manque)
    acquis = 0
    for url, dest, taille, sha in manque:
        base = acquis
        telecharger(url, dossier / dest, taille, lambda f, t, base=base, dest=dest: suivi(base + f, total, dest), sha, annule)
        acquis += taille
    suivi(total, total, "")


def _fenetre_premier(cfg):
    """Affiche la fenetre et telecharge. Retourne True si tout est la, False si l'utilisateur a quitte ou si ca a echoue."""
    manque = a_telecharger(groupes_voulus(cfg))
    if not manque:
        return True
    import tkinter as tk
    from hear_agent import Annule
    total = sum(t for _, _, t, _ in manque)
    libre = espace_libre(hear_config.DONNEES)
    fen = tk.Tk()
    fen.title("Hear")
    fen.configure(bg="#1c1c1e")
    fen.resizable(False, False)
    fen.attributes("-topmost", True)
    l, h = 460, 214
    fen.geometry(f"{l}x{h}+{(fen.winfo_screenwidth() - l) // 2}+{(fen.winfo_screenheight() - h) // 2}")
    try:
        fen.iconbitmap(str(hear_config.APP / "logo.ico"))
    except Exception:
        pass
    tk.Label(fen, text="Setting up Hear", fg="#f5f5f7", bg="#1c1c1e", font=("Segoe UI Semibold", 15)).pack(pady=(22, 2))
    sous = tk.Label(fen, text=f"Downloading the voice models, once ({_mo(total)}).\nAfter that, dictation works without internet.",
                    fg="#a1a1a6", bg="#1c1c1e", font=("Segoe UI", 10), justify="center")
    sous.pack()
    barre = tk.Canvas(fen, width=l - 70, height=8, bg="#3a3a3c", highlightthickness=0)
    barre.pack(pady=(18, 8))
    plein = barre.create_rectangle(0, 0, 0, 8, fill="#30d158", width=0)
    etat_txt = tk.Label(fen, text="Starting…", fg="#f5f5f7", bg="#1c1c1e", font=("Segoe UI", 10))
    etat_txt.pack()
    boutons = tk.Frame(fen, bg="#1c1c1e")
    boutons.pack(pady=(12, 0))
    etat = {"f": 0, "t": total, "fin": None, "fait": False}
    annule = threading.Event()

    def style(b):
        b.configure(bg="#2c2c2e", fg="#f5f5f7", activebackground="#3a3a3c", activeforeground="#f5f5f7",
                    relief="flat", bd=0, padx=16, pady=5, font=("Segoe UI", 10), cursor="hand2")
        return b

    def travail():
        try:
            if libre < total + MARGE_DISQUE:
                raise OSError(f"Not enough free disk space: {_mo(total)} needed, {_mo(libre)} available.")
            telecharger_tout(manque, lambda f, t, n: etat.update(f=f, t=t), annule)
            etat["fin"] = "ok"
        except Annule:
            etat["fin"] = "annule"
        except Exception as e:
            log("first launch download failed\n" + traceback.format_exc())
            etat["msg"] = str(e) if isinstance(e, OSError) and "disk" in str(e) else "The download didn't finish. Check your internet connection."
            etat["fin"] = "ko"

    def lancer():
        for w in boutons.winfo_children():
            w.destroy()
        etat.update(fin=None)
        annule.clear()
        style(tk.Button(boutons, text="Quit", command=quitter)).pack(side="left")
        threading.Thread(target=travail, daemon=True).start()

    def quitter():
        annule.set()
        etat["fait"] = False
        fen.after(150, fen.destroy)

    def suivre():
        f, t = etat["f"], max(1, etat["t"])
        barre.coords(plein, 0, 0, (l - 70) * min(1.0, f / t), 8)
        if etat["fin"] is None:
            etat_txt.configure(text=f"{_mo(f)} of {_mo(t)}   ·   {100 * f // t}%")
        elif etat["fin"] == "ok":
            etat["fait"] = True
            etat_txt.configure(text="Done. Starting Hear…")
            fen.after(500, fen.destroy)
            return
        elif etat["fin"] == "ko":
            etat_txt.configure(text=etat.get("msg", "The download didn't finish."), wraplength=l - 60)
            etat["fin"] = "attente"
            for w in boutons.winfo_children():
                w.destroy()
            style(tk.Button(boutons, text="Try again", command=lancer)).pack(side="left", padx=4)
            style(tk.Button(boutons, text="Quit", command=quitter)).pack(side="left", padx=4)
        elif etat["fin"] == "annule":
            return
        fen.after(100, suivre)

    fen.protocol("WM_DELETE_WINDOW", quitter)
    lancer()
    fen.after(100, suivre)
    fen.mainloop()
    try:
        fen.destroy()
    except Exception:
        pass                                    # deja detruite par le bouton de fermeture
    return etat["fait"]


def premier_lancement(cfg):
    """Affiche la fenetre et telecharge (voir _fenetre_premier). Retourne True si tout est la.
    Le ramasse-miettes tourne ICI, dans le fil principal, une fois la fonction de la fenetre terminee : l'interpreteur Tcl
    de la fenetre doit etre supprime par le fil qui l'a cree. Sinon il l'est plus tard depuis un autre fil et Tcl plante tout
    le programme (« Tcl_AsyncDelete: async handler deleted by the wrong thread », exception 0x80000003), des que Hear
    ouvre son interface juste apres le premier lancement."""
    resultat = _fenetre_premier(cfg)
    import gc
    gc.collect()
    return resultat
