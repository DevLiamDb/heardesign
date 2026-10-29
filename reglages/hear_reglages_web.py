"""Fenetre de reglages en HTML/CSS/JS (pywebview). Lancee par Hear dans un processus a part.
Elle ne touche jamais config.json : elle envoie ses changements a Hear via reglages_cmd.jsonl."""
import ctypes
import json
import os
import sys
import time
import traceback
from pathlib import Path

import webview  # noqa: E402

import hear_config  # noqa: E402
import hear_maj  # noqa: E402
from hear_config import LANGUES, autostart_actif, autostart_regler  # noqa: E402

DOSSIER = hear_config.APP                 # le programme : page HTML, icones, version
DATA = hear_config.DONNEES                # les donnees : reglages, memoire, echanges avec Hear
CONFIG = DATA / "config.json"
CMD = DATA / "reglages_cmd.jsonl"
MODE = "assistant" if "assistant" in sys.argv[1:] else "dictee"
MODE_COURANT = MODE
FRONT = DATA / "reglages_front.flag"
PAGE = DATA / "reglages_page.txt"


def log(msg):
    hear_config.log(f"[settings] {msg}")


class Api:
    dernier_cfg = {}

    def etat(self):
        cfg = None
        for _ in range(3):
            try:
                cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                time.sleep(0.03)
        if cfg is None:
            cfg = self.dernier_cfg
        self.dernier_cfg = cfg
        try:
            etat_hear = json.loads((DATA / "etat_hear.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            etat_hear = {}
        return {
            "occupe": bool(etat_hear.get("occupe")),
            "agent": etat_hear.get("agent") or {"etat": "absent"},
            "vision": etat_hear.get("vision") or {"etat": "absent"},
            "ultra": etat_hear.get("ultra") or {"etat": "absent"},
            "precise": etat_hear.get("precise") or {"etat": "absent"},
            "charge": etat_hear.get("charge") or {},
            "coeurs": os.cpu_count() or 4,
            "threads_permis": hear_config.threads_permis(),
            "memoire": self.memoire(),
            "journal": self.journal(),
            "cfg": cfg,
            "canary": (DATA / "model_canary" / "vocab.txt").exists(),
            "lid": (DATA / "model_lid" / "vocab.json").exists(),
            "autostart": autostart_actif(),
            "langues": [list(x) for x in LANGUES],
            "version": hear_maj.version_locale(DOSSIER),
            "version_active": etat_hear.get("version"),
            "maj": self.maj_etat(),
            "donnees": str(DATA),
            "magasin": hear_config.MAGASIN,
        }

    def ouvrir_site(self):
        """Ouvre le site officiel dans le navigateur (une seule adresse, fixe : rien d'autre ne peut etre ouvert d'ici)."""
        import webbrowser
        return bool(webbrowser.open("https://hear.devliam.com/"))

    def donnees_taille(self):
        """Place prise par les fichiers de Hear (modeles compris), en octets."""
        return hear_config.taille_dossier(DATA)

    def choisir_dossier(self):
        """« Change… » : choix d'un dossier, puis verification (place libre, droits d'ecriture, dossier vide)."""
        try:
            choix = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG, directory=str(DATA.parent))
        except Exception:
            log(traceback.format_exc())
            return {"erreur": "Couldn't open the folder picker."}
        if not choix:
            return {}
        cible = hear_config.cible_donnees(choix[0] if isinstance(choix, (list, tuple)) else choix)
        erreur = hear_config.verifier_cible(cible)
        return {"cible": str(cible), "erreur": erreur} if erreur else {"cible": str(cible)}

    def deplacer_donnees(self, cible):
        """Note le deplacement et redemarre Hear : les fichiers sont deplaces avant que rien ne soit charge."""
        try:
            cible = Path(cible)
            erreur = hear_config.verifier_cible(cible)
            if erreur:
                return {"erreur": erreur}
            hear_config.demander_deplacement(cible)
            with CMD.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"k": "@relancer"}) + "\n")
            return {"ok": True}
        except Exception:
            log(traceback.format_exc())
            return {"erreur": "Couldn't prepare the move."}

    def maj_etat(self):
        try:
            return json.loads((DATA / "maj_etat.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def prompt_defaut(self):
        try:
            import hear_agent
            return hear_agent.consigne_defaut()
        except Exception:
            log(traceback.format_exc())
            return "Not available."

    def univers(self, mode):
        """Le mode affiche change : icone et titre de la fenetre."""
        global MODE_COURANT
        MODE_COURANT = "assistant" if mode == "assistant" else "dictee"
        try:
            fen = webview.windows[0]
            fen.set_title("Hear Assistant" if MODE_COURANT == "assistant" else "Hear")
            hwnd = fen.native.Handle.ToInt32()
            icone(hwnd, MODE_COURANT)
        except Exception:
            log(traceback.format_exc())

    def memoire(self):
        try:
            faits = json.loads((DATA / "agent_memoire.json").read_text(encoding="utf-8")).get("faits", [])
            return [{"t": str(f.get("t", ""))[:200]} for f in faits if isinstance(f, dict) and f.get("t")]
        except (OSError, ValueError):
            return []

    def journal(self):
        try:
            e = json.loads((DATA / "agent_journal.json").read_text(encoding="utf-8")).get("entrees", [])
            return [x for x in e if isinstance(x, dict)][-40:][::-1]
        except (OSError, ValueError):
            return []

    def regler(self, cle, valeur):
        try:
            if cle == "autostart":
                autostart_regler(bool(valeur))
            else:
                with CMD.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"k": cle, "v": valeur}) + "\n")
        except Exception:
            log(traceback.format_exc())

    def page(self):
        return MODE

    def ouvrir(self, page):
        pass

    def touche(self):
        with CMD.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"k": "@touche"}) + "\n")

    def fermer(self):
        fenetre.destroy()


def icone(hwnd, mode=None):
    """Icone du mode (Hear ou Assistant) dans la barre des taches et la fenetre (au lieu de celle de Python)."""
    try:
        mode = mode or MODE
        chemin = str(DOSSIER / ("agent.ico" if mode == "assistant" and (DOSSIER / "agent.ico").exists() else "logo.ico"))
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        grande = user32.LoadImageW(None, chemin, 1, 256, 256, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        petite = user32.LoadImageW(None, chemin, 1, 32, 32, 0x10)
        if grande:
            user32.SendMessageW(hwnd, 0x80, 1, grande)  # WM_SETICON, ICON_BIG
            user32.SetClassLongPtrW(hwnd, -14, grande)
        if petite:
            user32.SendMessageW(hwnd, 0x80, 0, petite)  # ICON_SMALL
            user32.SetClassLongPtrW(hwnd, -34, petite)
    except Exception:
        log(traceback.format_exc())


def arrondir(fen):
    """Coins arrondis et mode sombre Windows 11 (sans effet ailleurs)."""
    try:
        time.sleep(0.4)
        hwnd = fen.native.Handle.ToInt32()
        icone(hwnd)
        dwm = ctypes.windll.dwmapi
        for attr, val in ((33, 2), (20, 1)):
            v = ctypes.c_int(val)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
    except Exception:
        pass


def surveiller(fen):
    """Hear ecrit un fichier-drapeau quand on rappelle les reglages : on remet la fenetre devant."""
    arrondir(fen)
    while True:
        time.sleep(0.3)
        if getattr(fen, "closed_flag", False):
            return
        try:
            if FRONT.exists():
                FRONT.unlink()
                try:
                    voulu = PAGE.read_text(encoding="utf-8").strip() if PAGE.exists() else ""
                    if voulu in ("assistant", "dictee") and voulu != MODE_COURANT:
                        fen.evaluate_js("window.changerUnivers && window.changerUnivers('" + voulu + "')")
                except Exception:
                    log(traceback.format_exc())
                fen.restore()
                fen.on_top = True
                time.sleep(0.25)
                fen.on_top = False
        except Exception:
            pass


def main():
    global fenetre
    try:
        FRONT.unlink(missing_ok=True)
        try:  # identite propre : la barre des taches groupe sous "Hear" avec son icone
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hear.Settings")
        except Exception:
            pass
        options = dict(width=760, height=790, resizable=False, frameless=True, easy_drag=False,
                       background_color="#1e1e20", js_api=Api())
        try:
            fenetre = webview.create_window("Hear Assistant" if MODE == "assistant" else "Hear", str(DOSSIER / "reglages.html"), shadow=True, **options)
        except TypeError:
            fenetre = webview.create_window("Hear Assistant" if MODE == "assistant" else "Hear", str(DOSSIER / "reglages.html"), **options)
        webview.start(surveiller, fenetre)
        os._exit(0)  # la fenetre est fermee : on quitte vraiment (le fil de surveillance ne doit pas rester vivant)
    except Exception:
        log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
