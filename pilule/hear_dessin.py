"""Dessin de Hear : la pilule, la carte de reponse, les details, les icones et les fenetres en couches (Windows).

Tout est rendu avec PIL/numpy en images RGBA. L'etat partage avec la boucle principale (texte tape, mot affiche
pendant que l'assistant travaille, regard des yeux...) vit dans les variables de module ci-dessous : hear.py les
modifie via `hear_dessin.NOM = ...`."""
import ctypes
import math
import sys
import threading
import traceback
import urllib.parse

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from hear_config import DOSSIER, log

S = 3
DEPART = 16.0
PILULE = (8, 8, 10)
BORD = (40, 40, 45)
BLANC = (245, 245, 247)
GRIS = (142, 142, 147)
ROUGE = (255, 69, 58)
ORANGE = (255, 159, 10)
VERT = (48, 209, 88)
BLEU = (10, 132, 255)
TEINTE_AGENT = (238, 238, 238)   # tout reste noir et blanc
VEILLE = (0.0, 0.0, 0.0, 0.0)       # pilule permanente : (eveil 0..1, clignement 0..1, regard x, regard y)
TEXTE_HOVER = None                 # "mic" / "envoi" quand la souris survole une icone de la pilule de texte
TEXTE_PJ = ""                      # puce "texte selectionne" jointe a la question
TEXTE_INVITE = "Ask anything"      # texte gris du champ vide
TEXTE_SAISIE = ("", 0)             # texte tape dans la bulle de saisie, et position du curseur

MOT_LANGUE = ""
MOT_AVERTIR = ""      # message d'une fonction coupee (croix rouge)
T_ETAT = 0.0          # instant ou la pilule est entree dans son etat : sert au trace des coches et des croix
ANIME = True          # faux quand Windows demande moins d'animations : tout s'affiche d'un coup
ETAPES_INFO = []      # un dict par outil lance pour la question en cours : mot, t0, t1 (fini), arg, res (voir boule_action)
HOV = {"mic": 0.0, "envoi": 0.0}   # survol des icones de la pilule de texte, adouci (0..1)
MOT_AGENT = ""
NOIR_ = (0, 0, 0)


def mode_de(texte):
    """Quelle animation : atome (il reflechit), fic (document + loupe), mem (reseau), web (globe), pc (fenetre + curseur),
    ou None (ondes)."""
    m = texte or ""
    if m.startswith("Thinking"):
        return "atome"
    if m.startswith(("Looking for the file", "Searching in your files", "Reading the file", "Opening the file")):
        return "fic"
    if m.startswith(("Saving to memory", "Updating memory", "Updating your to-do", "Searching memory", "Remembering")):
        return "mem"
    if m.startswith(("Searching", "Reading the page", "Looking at the page", "Checking the weather", "Opening the page")):
        return "web"
    if m.startswith(("Opening", "Looking at your windows", "Looking at your screen", "Reading your clipboard")):
        return "pc"
    return None


def mode_agent():
    """Quel dessin pour l'etat 'agent' : web (globe), pc (fenetre + curseur), mem (reseau), fic (document), ou None (ondes)."""
    return mode_de(MOT_AGENT)


COMPACT = False

TEXTES = {
    "chargement": "Please wait, loading the model…",
    "transcription": "Transcribing…",
    "rebind": "Press the new key",
    "vide": "Nothing heard",
}


def charger_police(taille):
    for nom in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nom, taille)
        except OSError:
            continue
    return ImageFont.load_default()


def melange(couleur, a):
    return tuple(int(PILULE[i] + (couleur[i] - PILULE[i]) * a) for i in range(3))


def taille_cible(etat, police):
    """Pilule au repos : forme trapue (environ 1,5 fois plus large que haute), comme une petite capsule."""
    if etat in ("pret", "eveil"):
        return 70 + 8, 45 + 8
    return _taille_brute(etat, police)


def _taille_brute(etat, police):
    texte = TEXTES.get(etat)
    if etat in ("chargement", "transcription"):
        return int(94 + police.getlength(texte) / S), 40
    if etat == "agent":
        return int(94 + police.getlength(MOT_AGENT) / S), 40
    if texte:
        return int(58 + police.getlength(texte) / S), 40
    if etat == "copie":
        return int(66 + police.getlength("Copied") / S), 40
    if etat == "langue":
        return int(66 + police.getlength(MOT_LANGUE) / S), 40
    if etat == "avertir":
        return int(66 + police.getlength(MOT_AVERTIR) / S), 40
    if etat == "texte":
        return 250, 46
    if etat == "ecoute":
        return (150, 38) if COMPACT else (210, 46)
    if etat in ("pret", "eveil"):
        return 62, 43
    return 72, 40


def icone_action(d, mode, gx_, cy, t, vis, e=1.0):
    """L'animation d'un outil, centree en (gx_, cy) : web (globe), pc (fenetre + curseur), mem (reseau),
    fic (document + loupe), sinon des ondes. e : echelle (1 dans la pilule, ~0.6 dans une boule)."""
    Se = S * e
    lw = max(1, int(1.25 * Se))
    c_ = melange(BLANC, vis * 0.92)
    if mode == "pc":            # action sur le PC : une mini fenetre, un curseur qui se deplace et clique
        fx0, fy0, fx1, fy1 = gx_ - 12 * Se, cy - 9 * Se, gx_ + 12 * Se, cy + 9 * Se
        d.rounded_rectangle((fx0, fy0, fx1, fy1), radius=3 * Se, outline=c_, width=lw)
        d.line((fx0, fy0 + 4.5 * Se, fx1, fy0 + 4.5 * Se), fill=c_, width=lw)
        for k_ in range(3):
            d.ellipse((fx0 + (2.2 + 2.6 * k_) * Se - 0.7 * Se, fy0 + 2.25 * Se - 0.7 * Se,
                       fx0 + (2.2 + 2.6 * k_) * Se + 0.7 * Se, fy0 + 2.25 * Se + 0.7 * Se), fill=c_)
        ph = (t * 0.8) % 1.0                       # 0..1 : le curseur glisse puis clique
        glisse = min(1.0, ph / 0.6)
        glisse = glisse * glisse * (3 - 2 * glisse)
        px_ = fx0 + (4 + 11 * glisse) * Se
        py_ = fy0 + (14 - 5 * glisse) * Se
        if ph > 0.6:                               # onde du clic
            u_ = (ph - 0.6) / 0.4
            rr = (1.5 + 6 * u_) * Se
            d.ellipse((px_ - rr, py_ - rr, px_ + rr, py_ + rr), outline=melange(BLANC, vis * 0.9 * (1 - u_)), width=lw)
        pts = [(px_, py_), (px_, py_ + 8 * Se), (px_ + 2 * Se, py_ + 6 * Se), (px_ + 4.6 * Se, py_ + 6 * Se)]
        d.polygon(pts, fill=melange(BLANC, vis), outline=melange(NOIR_, vis))
    elif mode == "mem":         # memoire : un petit reseau de points ou une impulsion circule
        noeuds = [(-9, -4), (-2, 6), (8, 3), (4, -7), (-3, -1)]
        liens = [(0, 4), (4, 1), (4, 3), (1, 2), (2, 3)]
        for a_, b_ in liens:
            d.line((gx_ + noeuds[a_][0] * Se, cy + noeuds[a_][1] * Se, gx_ + noeuds[b_][0] * Se, cy + noeuds[b_][1] * Se),
                   fill=melange(BLANC, vis * 0.35), width=max(1, int(1.1 * Se)))
        for i_, (nx_, ny_) in enumerate(noeuds):
            pul = 0.5 + 0.5 * math.sin(t * 3.2 - i_ * 1.25)
            r_ = (1.7 + 1.5 * pul) * Se
            d.ellipse((gx_ + nx_ * Se - r_, cy + ny_ * Se - r_, gx_ + nx_ * Se + r_, cy + ny_ * Se + r_),
                      fill=melange(BLANC, vis * (0.45 + 0.55 * pul)))
    elif mode == "web":         # web : des points arrivent de partout vers le centre, comme des informations qu'on rassemble
        for i_ in range(10):
            a_ = i_ * 2 * math.pi / 10 + 0.3
            u_ = (t * 0.75 + i_ * 0.1) % 1.0
            f_ = u_ * u_ * (3 - 2 * u_)
            r_ = (11.5 * (1 - f_) + 2.2 * f_) * Se
            al_ = math.sin(math.pi * min(1.0, u_ * 1.15)) ** 0.8
            rr_ = (1.8 - 0.8 * f_) * Se
            x_, y_ = gx_ + r_ * math.cos(a_), cy + r_ * math.sin(a_) * 0.9
            d.ellipse((x_ - rr_, y_ - rr_, x_ + rr_, y_ + rr_), fill=melange(BLANC, vis * al_))
        pul = 0.5 + 0.5 * math.sin(t * 4.5)
        rc_ = (2.3 + 0.6 * pul) * Se
        d.ellipse((gx_ - rc_, cy - rc_, gx_ + rc_, cy + rc_), fill=melange(BLANC, vis))
    elif mode == "fic":         # recherche dans les dossiers : une loupe parcourt une grille de fichiers qui s'allument
        lx = gx_ + 5.5 * math.sin(t * 1.7) * Se
        ly = cy + 2.8 * math.sin(t * 2.3 + 0.8) * Se
        for i_ in range(5):
            for j_ in range(3):
                x_, y_ = gx_ + (i_ - 2) * 4.8 * Se, cy + (j_ - 1) * 4.8 * Se
                f_ = max(0.0, 1 - math.hypot(x_ - lx, y_ - ly) / (6.5 * Se))
                r_ = (1.0 + 0.9 * f_) * Se
                d.ellipse((x_ - r_, y_ - r_, x_ + r_, y_ + r_), fill=melange(BLANC, vis * (0.22 + 0.75 * f_)))
        r_ = 5.2 * Se
        d.ellipse((lx - r_, ly - r_, lx + r_, ly + r_), outline=c_, width=lw)
        d.line((lx + r_ * 0.72, ly + r_ * 0.72, lx + r_ * 0.72 + 4.0 * Se, ly + r_ * 0.72 + 4.0 * Se), fill=c_, width=max(1, int(1.6 * Se)))
    elif mode == "atome":       # il reflechit : un noyau qui bat, trois orbites qui tournent doucement, des electrons avec une traine
        a_, b_ = 11.0 * Se, 4.3 * Se
        tourne = t * 0.35                                           # tout l'atome pivote lentement
        for n_ in range(3):
            phi = tourne + n_ * math.pi / 3
            cphi, sphi = math.cos(phi), math.sin(phi)
            orbite = []
            for j in range(41):
                th = 2 * math.pi * j / 40
                ox, oy = a_ * math.cos(th), b_ * math.sin(th)
                orbite.append((gx_ + ox * cphi - oy * sphi, cy + ox * sphi + oy * cphi))
            d.line(orbite, fill=melange(BLANC, vis * 0.38), width=lw, joint="curve")
            for q in range(5):                                      # l'electron et sa traine
                th = t * (2.6 + 0.45 * n_) + n_ * 2.1 - q * 0.14
                ox, oy = a_ * math.cos(th), b_ * math.sin(th)
                ex, ey = gx_ + ox * cphi - oy * sphi, cy + ox * sphi + oy * cphi
                rr = (1.75 - 0.27 * q) * Se
                d.ellipse((ex - rr, ey - rr, ex + rr, ey + rr), fill=melange(BLANC, vis * (0.95 - 0.17 * q)))
        pul = 0.5 + 0.5 * math.sin(t * 3.4)
        rn = (2.2 + 0.5 * pul) * Se
        d.ellipse((gx_ - rn, cy - rn, gx_ + rn, cy + rn), fill=melange(BLANC, vis * (0.8 + 0.2 * pul)))
    else:                       # sans categorie : cinq petites ondes
        for i in range(5):
            centre = 1 - abs(2 * i / 4 - 1)
            h = (3 + 12 * (0.5 + 0.5 * math.sin(t * 4.5 - i * 0.7)) * (0.35 + 0.65 * centre)) * e
            x = gx_ + (i - 2) * 5.5 * Se
            d.rounded_rectangle((x - 1.5 * Se, cy - h / 2 * S, x + 1.5 * Se, cy + h / 2 * S), radius=1.5 * Se, fill=c_)


def boule_action(etape, t, k, hov):
    """Une boule ronde (comme les boutons pause / envoi) pour un outil de l'assistant : son animation, un arc qui tourne
    tant qu'il travaille, une coche une fois fini. Au survol (hov 0..1) elle s'etire en capsule : ce qu'il fait et
    ce qu'il a ecrit. etape : {"mot", "t0", "t1" (None tant qu'il travaille), "arg", "res"}."""
    mot = etape.get("mot", "")
    fini = etape.get("t1") is not None
    mode = mode_de(mot)
    l1 = mot.rstrip("…").rstrip(".").strip() if fini else mot
    l2 = etape.get("arg") or etape.get("res") or ""
    f1, f2 = police_cache(round(12.5 * S)), police_cache(round(11 * S))
    pleine = 6 + min(200.0, max(f1.getlength(l1), f2.getlength(l2)) / S) + 14
    larg, haut = 38 + hov * pleine, 38 + (hov * 8 if l2 else 0)
    W, H = max(2, round(larg * S)), max(2, round(haut * S))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = int(30 + 10 * hov)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=H // 2, fill=(g, g, g + 4), outline=BORD, width=S)
    cx, cy = 19 * S, H / 2
    gel = etape.get("t1") if fini else t                  # une boule finie garde sa derniere image
    icone_action(d, mode, cx, cy, gel, 0.6 if fini else 1.0, e=0.6)
    if not fini:                                          # il travaille : un arc tourne autour
        debut = (t * 220) % 360
        d.arc((cx - 17 * S, cy - 17 * S, cx + 17 * S, cy + 17 * S), debut, debut + 85, fill=melange(BLANC, 0.55), width=max(1, int(1.3 * S)))
    else:                                                 # fini : une petite coche blanche
        bx, by, br = cx + 12.5 * S, cy + 12.5 * S, 5.2 * S
        d.ellipse((bx - br, by - br, bx + br, by + br), fill=(238, 238, 242), outline=PILULE[:3], width=S)
        d.line([(bx - 2.3 * S, by + 0.1 * S), (bx - 0.6 * S, by + 1.9 * S), (bx + 2.4 * S, by - 1.7 * S)],
               fill=(20, 20, 22), width=max(1, int(1.4 * S)), joint="curve")
    a_txt = min(1.0, max(0.0, (hov - 0.35) / 0.5))
    if a_txt > 0:
        xt = 40 * S
        place = W - xt - 10 * S
        d.text((xt, cy - (7 * S if l2 else 0)), coupe_ligne(l1, f1, place), font=f1, fill=melange(BLANC, a_txt), anchor="lm")
        if l2:
            d.text((xt, cy + 8 * S), coupe_ligne(l2, f2, place), font=f2, fill=melange((150, 150, 156), a_txt), anchor="lm")
    return img.resize((max(2, round(W / S * k)), max(2, round(H / S * k))), Image.LANCZOS)


def rangee_boules(etapes, t, k, hovs, alpha=1.0):
    """Les boules cote a cote (au plus celles qu'on passe). Retourne (image, [(x0, y0, x1, y1) de chaque boule dans l'image])."""
    ecart = max(1, round(8 * k))
    imgs = [boule_action(e, t, k, h) for e, h in zip(etapes, hovs)]
    H = max(i.size[1] for i in imgs)
    W = sum(i.size[0] for i in imgs) + ecart * (len(imgs) - 1)
    bande = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rects, x = [], 0
    for e, im in zip(etapes, imgs):
        w_, h_ = im.size
        u = sortie_forte((t - e.get("t0", t)) / 0.22) if ANIME else 1.0      # une nouvelle boule grossit en apparaissant
        y_ = (H - h_) // 2
        rects.append((x, y_, x + w_, y_ + h_))
        if u < 1.0 or alpha < 1.0:
            s = 0.7 + 0.3 * u
            im2 = im.resize((max(2, round(w_ * s)), max(2, round(h_ * s))), Image.LANCZOS)
            a = np.asarray(im2.split()[3], dtype=np.float32) * (u * alpha)
            im2.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
            bande.alpha_composite(im2, (x + (w_ - im2.size[0]) // 2, (H - im2.size[1]) // 2))
        else:
            bande.alpha_composite(im, (x, y_))
        x += w_ + ecart
    return bande, rects


def sortie_forte(x):
    """Demarrage vif, arrivee douce (ease-out) : x de 0 a 1."""
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 4


def progres_trace(t, delai=0.08, duree=0.24):
    """Avancement du trace d'une coche ou d'une croix : elle se dessine pendant que la pilule finit de s'ajuster."""
    if not ANIME:
        return 1.0
    return sortie_forte((t - T_ETAT - delai) / duree)


def trace(pts, frac):
    """La ligne brisee pts, tracee sur la fraction frac (0..1) de sa longueur."""
    if frac >= 1.0:
        return list(pts)
    long = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    reste = frac * sum(long)
    sortie = [pts[0]]
    for i, seg in enumerate(long):
        if reste >= seg:
            sortie.append(pts[i + 1])
            reste -= seg
        else:
            f = reste / seg if seg else 0.0
            sortie.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f))
            break
    return sortie


def coche(d, pts, couleur, epaisseur, t):
    f = progres_trace(t)
    if f > 0.001:
        d.line(trace(pts, f), fill=couleur, width=epaisseur, joint="curve")


def trait_rond(d, a, b, f, couleur, w):
    """Un trait aux bouts arrondis, trace de a vers b sur la fraction f."""
    if f <= 0.001:
        return
    e = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
    d.line([a, e], fill=couleur, width=w)
    for x, y in (a, e):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=couleur)


def pilule(etat, t, lisse, police, largeur, hauteur, k=1.0, vis=1.0, histo=None, frac=0.0, agent=False):
    texte = MOT_AGENT if etat == "agent" else TEXTES.get(etat)
    taille = (largeur * S, hauteur * S)
    img = Image.new("RGBA", taille, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = hauteur * S / 2
    cx = largeur * S / 2
    d.rounded_rectangle((0, 0, taille[0] - 1, taille[1] - 1),
                        radius=hauteur * S // 2, fill=PILULE, outline=BORD, width=S)
    if etat == "ecoute":
        reflet = np.linspace(26, 0, taille[1], dtype=np.float32) ** 1.0
        reflet = np.clip(reflet, 0, 26)
        alpha = np.tile(reflet[:, None], (1, taille[0]))
        forme = np.array(img.split()[3], dtype=np.float32) / 255.0
        lum = Image.new("RGBA", taille, (255, 255, 255, 0))
        lum.putalpha(Image.fromarray((alpha * forme * 0.5).astype(np.uint8), "L"))
        img.alpha_composite(lum)
        d = ImageDraw.Draw(img)

    if etat == "ecoute" and histo:
        pas = 5.0
        gauche, droite = largeur * 0.2, largeur * 0.8
        n = int((droite - gauche) / pas) + 3
        vals = list(histo)[-n:]
        vals = [0.0] * (n - len(vals)) + vals
        lis = [(vals[max(i - 1, 0)] + 2 * vals[i] + vals[min(i + 1, n - 1)]) / 4 for i in range(n)]
        xd = droite
        for i, v in enumerate(lis):
            xp = xd - (n - 1 - i) * pas - frac * pas
            bord = min(xp - gauche, droite - xp) / 30.0
            bord = min(1.0, max(0.0, bord))
            bord = bord * bord * (3 - 2 * bord)
            if bord <= 0.01:
                continue
            h = 3 + 26 * min(1.0, v) ** 0.9
            clair = (0.5 + 0.5 * min(1.0, v * 1.3)) * bord * vis
            x = xp * S
            d.rounded_rectangle((x - 1.5 * S, cy - h / 2 * S, x + 1.5 * S, cy + h / 2 * S),
                                radius=1.5 * S, fill=melange(TEINTE_AGENT if agent else BLANC, clair))
    elif etat == "ecoute":
        n = 25
        x0, x1 = 26, largeur - 26
        pas = (x1 - x0) / (n - 1)
        for i in range(n):
            centre = 1 - abs(2 * i / (n - 1) - 1)
            fondu = centre ** 1.3
            x = (x0 + i * pas) * S
            d.rounded_rectangle((x - 1.5 * S, cy - 1.5 * S, x + 1.5 * S, cy + 1.5 * S),
                                radius=1.5 * S, fill=melange(TEINTE_AGENT if agent else BLANC, fondu * 0.5 * vis))
    elif etat in ("pret", "eveil"):
        eveil, clig, gx, gy = VEILLE
        m = 4 * S                           # marge : une ombre douce sous la pilule, pas de relief
        ph = taille[1] - 2 * m
        d.rectangle((0, 0, taille[0], taille[1]), fill=(0, 0, 0, 0))
        ombre = Image.new("RGBA", taille, (0, 0, 0, 0))
        ImageDraw.Draw(ombre).rounded_rectangle((m + S, m + 2 * S, taille[0] - m - S, taille[1] - m + 1.5 * S), radius=ph // 2, fill=(0, 0, 0, 150))
        img.alpha_composite(ombre.filter(ImageFilter.GaussianBlur(2.6 * S)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((m, m, taille[0] - m - 1, taille[1] - m - 1), radius=ph // 2, fill=PILULE, outline=BORD, width=S)
        cy = taille[1] / 2
        ex, ey = gx * 2.0, gy * 1.2
        ecart = 8.6
        for sgn in (-1, 1):
            x = (cx / S + sgn * ecart + ex) * S
            y = cy + ey * S
            if eveil < 0.98:        # yeux fermes : petit arc en "U", tres doux
                a_ = (1 - eveil) * vis
                d.arc((x - 4.4 * S, y - 4.1 * S, x + 4.4 * S, y + 2.8 * S), 25, 155,
                      fill=melange(BLANC, a_), width=max(1, int(1.9 * S)))
            if eveil > 0.02:        # yeux ouverts : petits ovales debout qui clignent
                h = max(1.0, 9.6 * (1 - clig * 0.9)) * (0.4 + 0.6 * eveil)
                d.rounded_rectangle((x - 3.0 * S, y - h / 2 * S, x + 3.0 * S, y + h / 2 * S),
                                    radius=3.0 * S, fill=melange(BLANC, eveil * vis))
        if eveil < 0.9:             # les "z z z" du sommeil montent a droite des yeux et s'effacent
            for dec in (0.0, 0.33, 0.66):
                ph = ((t * 0.28) + dec) % 1.0
                al = math.sin(math.pi * ph) * (1 - eveil) * 0.8 * vis
                if al < 0.03:
                    continue
                z = (3.6 + 2.4 * ph) * S
                zx = (cx / S + 17 + ph * 9) * S
                zy = cy + (6 - ph * 13) * S
                d.line([(zx - z / 2, zy - z / 2), (zx + z / 2, zy - z / 2), (zx - z / 2, zy + z / 2), (zx + z / 2, zy + z / 2)],
                       fill=melange(BLANC, al), width=max(1, int(1.35 * S)), joint="curve")
    elif etat == "texte":
        txt, cur = TEXTE_SAISIE
        passif = cur < 0                    # champ de reponse sous la carte : pas de curseur, pas encore le clavier
        cur = max(0, cur)
        zl, zr = 46 * S, (largeur - 46) * S
        zw = max(2, int(zr - zl))          # pendant l'ouverture la pastille est encore etroite
        couche = Image.new("RGBA", (zw, taille[1]), (0, 0, 0, 0))
        dc = ImageDraw.Draw(couche)
        xc = police.getlength(txt[:cur])
        decal = max(0.0, xc + 3 * S - zw)
        if txt:
            dc.text((-decal, cy), txt, font=police, fill=melange(BLANC, vis), anchor="lm")
        else:
            dc.text((0, cy), "Reply" if passif else TEXTE_INVITE, font=police, fill=melange((110, 110, 116), vis), anchor="lm")
        if not passif and int(t / 0.53) % 2 == 0:
            xx = xc - decal
            dc.rounded_rectangle((xx, cy - 8.5 * S, xx + 1.7 * S, cy + 8.5 * S), radius=0.85 * S,
                                 fill=melange(TEINTE_AGENT, vis))
        rampe = np.ones(zw, np.float32)
        if decal > 0:
            n1 = min(zw, 22 * S)
            rampe[:n1] = np.linspace(0, 1, n1) ** 1.5
        al = np.asarray(couche.split()[3], dtype=np.float32) * rampe[None, :]
        couche.putalpha(Image.fromarray(al.astype(np.uint8), "L"))
        if zr - zl > 4 * S:
            img.alpha_composite(couche, (int(zl), 0))
        if largeur > 150:           # micro a gauche, envoi a droite : tout est dans la pilule
            gm = icone_svg("mic", round(15 * S), melange(BLANC, vis * (0.62 + 0.38 * HOV["mic"])))
            img.alpha_composite(gm, (int(23 * S - gm.size[0] / 2), int(cy - gm.size[1] / 2)))
            actif = bool(txt.strip())
            ce = melange(BLANC, vis * (0.9 + 0.1 * HOV["envoi"])) if actif else melange((88, 88, 94), vis)
            ge = icone_svg("envoi", round(22 * S), ce)
            img.alpha_composite(ge, (int((largeur - 23) * S - ge.size[0] / 2), int(cy - ge.size[1] / 2)))
    elif etat == "ok":
        coche(d, [(cx - 7 * S, cy + 0.5 * S), (cx - 2 * S, cy + 5 * S), (cx + 8 * S, cy - 6 * S)],
              melange(VERT, vis), int(2.6 * S), t)
    elif etat == "copie":
        mot = "Copied"
        total = 14 * S + 8 * S + police.getlength(mot)
        sx = (taille[0] - total) / 2
        coche(d, [(sx, cy + 0.5 * S), (sx + 4.5 * S, cy + 4.8 * S), (sx + 13.5 * S, cy - 5 * S)],
              melange(BLEU, vis), int(2.4 * S), t)
        d.text((sx + 22 * S, cy), mot, font=police, fill=melange(BLANC, vis), anchor="lm")
    elif etat == "langue":
        mot = MOT_LANGUE
        total = 14 * S + 8 * S + police.getlength(mot)
        sx = (taille[0] - total) / 2
        coche(d, [(sx, cy + 0.5 * S), (sx + 4.5 * S, cy + 4.8 * S), (sx + 13.5 * S, cy - 5 * S)],
              melange(VERT, vis), int(2.4 * S), t)
        d.text((sx + 22 * S, cy), mot, font=police, fill=melange(BLANC, vis), anchor="lm")
    elif etat == "avertir":
        mot = MOT_AVERTIR
        total = 14 * S + 8 * S + police.getlength(mot)
        sx = (taille[0] - total) / 2
        rouge, w = melange(ROUGE, vis), int(2.4 * S)
        mx = sx + 6.75 * S                    # une simple croix rouge, aux bouts arrondis
        p_ = progres_trace(t)                   # les deux branches se tracent l'une apres l'autre
        for n_, (x0, y0, x1, y1) in enumerate(((mx - 4.6 * S, cy - 4.6 * S, mx + 4.6 * S, cy + 4.6 * S),
                                               (mx - 4.6 * S, cy + 4.6 * S, mx + 4.6 * S, cy - 4.6 * S))):
            trait_rond(d, (x0, y0), (x1, y1), min(1.0, max(0.0, p_ * 2 - n_)), rouge, w)
        d.text((sx + 22 * S, cy), mot, font=police, fill=melange(BLANC, vis), anchor="lm")
    elif etat == "erreur":
        d.line([(cx, cy - 7 * S), (cx, cy + 1.5 * S)], fill=melange(ROUGE, vis), width=int(2.6 * S))
        d.ellipse((cx - 1.6 * S, cy + 5.4 * S, cx + 1.6 * S, cy + 8.6 * S), fill=melange(ROUGE, vis))
    elif etat in ("chargement", "agent", "transcription"):
        n = 9
        mode_ = mode_agent() if etat == "agent" else None
        web = mode_ == "web"
        if mode_:
            icone_action(d, mode_, 38 * S, cy, t, vis)
        for i in range(0 if mode_ else n):
            centre = 1 - abs(2 * i / (n - 1) - 1)
            h = 3 + 12 * (0.5 + 0.5 * math.sin(t * 4.5 - i * 0.7)) * (0.35 + 0.65 * centre)
            x = (20 + i * 5.5) * S
            d.rounded_rectangle((x - 1.5 * S, cy - h / 2 * S, x + 1.5 * S, cy + h / 2 * S),
                                radius=1.5 * S, fill=melange(TEINTE_AGENT if etat == "agent" else BLANC, vis * centre ** 1.3))
        x0 = 78 * S
        x1 = x0 + police.getlength(texte)
        bande = 36 * S
        pos = x0 - bande + (x1 - x0 + 2 * bande) * ((t / 1.5) % 1.0)
        colonnes = np.arange(taille[0], dtype=np.float32)
        lueur = np.exp(-(((colonnes - pos) / bande) ** 2))
        lueur_img = Image.fromarray(np.tile((lueur * 255).astype(np.uint8), (taille[1], 1)), "L")
        couleur = Image.composite(Image.new("RGB", taille, melange(BLANC, vis)), Image.new("RGB", taille, melange((112, 112, 118), vis)), lueur_img)
        masque = Image.new("L", taille, 0)
        ImageDraw.Draw(masque).text((x0, cy), texte, font=police, fill=255, anchor="lm")
        img.paste(couleur, (0, 0), masque)
    elif texte:
        pouls = 0.5 + 0.5 * math.sin(t * 4)
        couleur = ORANGE if etat == "rebind" else GRIS
        r = 4 * S
        d.ellipse((24 * S - r, cy - r, 24 * S + r, cy + r), fill=melange(couleur, (0.55 + 0.45 * pouls) * vis))
        d.text((38 * S, cy), texte, font=police, fill=melange(BLANC, vis), anchor="lm")

    return largeur, hauteur, img.resize((round(largeur * k), round(hauteur * k)), Image.LANCZOS)


def decouper(texte, police, largeur):
    """Retour a la ligne par mots, en pixels."""
    lignes = []
    for para in texte.split("\n"):
        mots, ligne = para.split(" "), ""
        for mot in mots:
            essai = (ligne + " " + mot).strip() if ligne else mot
            if ligne and police.getlength(essai) > largeur:
                lignes.append(ligne)
                ligne = mot
            else:
                ligne = essai
        lignes.append(ligne)
    return lignes


def coupe_ligne(texte, police, largeur):
    if police.getlength(texte) <= largeur:
        return texte
    while texte and police.getlength(texte + "\u2026") > largeur:
        texte = texte[:-1]
    return texte.rstrip() + "\u2026"


PALETTE_CARTE = [(250, 250, 252), (128, 130, 140), (238, 239, 244), (92, 94, 104), (250, 250, 252)]
CARTE_L = 440        # largeur de la carte (px logiques)
CARTE_PAD = 20
CARTE_HAUT = 18      # marge au-dessus du texte
CARTE_LIGNE = 21
CARTE_VMAX = 380     # hauteur max de la zone de texte
CARTE_RAYON = 28
CARTE_CTL = 44       # bande des boutons (copier / regenerer)
_lut_siri = None
_angles = {}
_polices = {}
_icones = {}


def police_cache(taille):
    taille = max(6, int(taille))
    if taille not in _polices:
        _polices[taille] = charger_police(taille)
    return _polices[taille]


def lut_siri(n=512):
    global _lut_siri
    if _lut_siri is None:
        xs = np.linspace(0, 1, len(PALETTE_CARTE))
        t = np.linspace(0, 1, n)
        _lut_siri = np.stack([np.interp(t, xs, [c[i] for c in PALETTE_CARTE]) for i in range(3)], axis=1).astype(np.float32)
    return _lut_siri


def angles(w, h):
    cle = (w, h)
    if cle not in _angles:
        if len(_angles) > 12:
            _angles.clear()
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        _angles[cle] = (np.arctan2(yy - h / 2, xx - w / 2) / (2 * np.pi) + 0.5).astype(np.float32)
    return _angles[cle]


def libelle_pj(sel):
    n = len(sel.split())
    return "Selected text · %d word%s" % (n, "" if n == 1 else "s")


class Lignes(list):
    """Les lignes de la conversation ; .zones : pour chaque echange, la hauteur de sa question et de sa reponse (survol)."""
    zones = ()


def fil_mise_en_page(tours, k):
    """Toute la conversation en lignes. Retourne (lignes, hauteur, derniere_reponse)."""
    ss = 2 * k
    p_req, p_txt = police_cache(12.5 * ss), police_cache(15 * ss)
    larg = (CARTE_L - 2 * CARTE_PAD) * ss
    y, rows, dern, zones = 0.0, Lignes(), None, []
    for i, t in enumerate(tours):
        yq = y
        if t.get("q_ouvert"):
            for lg in decouper(t["q"], p_req, larg - 34 * ss) or [""]:        # la question en entier, sur plusieurs lignes
                rows.append(("q", lg, y))
                y += 20
            y += 4
        else:
            rows.append(("q", coupe_ligne(t["q"], p_req, larg - 34 * ss), y))
            y += 24
        zq = (yq, y)
        if t.get("sel"):
            rows.append(("pj", libelle_pj(t["sel"]), y))
            y += 24
        za = None
        if t["r"]:
            lignes = decouper(t["r"], p_txt, larg)
            debut, starts, c = y, [], 0
            for lg in lignes:
                rows.append(("r", lg, y))
                starts.append(c)
                c += len(lg) + 1
                y += CARTE_LIGNE
            if i == len(tours) - 1:
                dern = {"lignes": lignes, "starts": starts, "y0": debut}
            za = (debut, y)
        elif t.get("statut_carte"):
            rows.append(("s", t["statut"], y))
            y += CARTE_LIGNE
        zc = None
        if t.get("confirmer") and t.get("final") and i == len(tours) - 1:
            zc = (y, y + 38)                      # une rangee pour les boutons Oui / Non sous la question de confirmation
            y += 38
        zones.append({"i": i, "q": zq, "r": za, "c": zc})
        y += 14
    rows.zones = zones
    return rows, max(24.0, y - 14), dern


def fil_couche(rows, haut, k):
    ss = 2 * k
    larg, hh = round((CARTE_L - 2 * CARTE_PAD) * ss), round((haut + 8) * ss)
    img = Image.new("RGBA", (larg, hh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p_req, p_txt = police_cache(12.5 * ss), police_cache(15 * ss)
    for genre, txt, y in rows:
        if genre == "r":
            d.text((0, y * ss), txt, font=p_txt, fill=(246, 246, 248, 255))
        elif genre == "pj":
            p_pj = police_cache(11 * ss)
            ic = max(8, round(13 * ss))
            w = round(p_pj.getlength(txt) + 12 * ss + ic + 8 * ss)
            y0, y1 = round((y - 2) * ss), round((y + 17) * ss)
            d.rounded_rectangle((0, y0, w, y1), radius=(y1 - y0) // 2, fill=(255, 255, 255, 26))
            img.alpha_composite(icone_svg("texte_sel", ic, (170, 170, 178)), (round(7 * ss), (y0 + y1 - ic) // 2))
            d.text((round(7 * ss) + ic + round(5 * ss), (y0 + y1) / 2), txt, font=p_pj, fill=(170, 170, 178, 255), anchor="lm")
        else:
            d.text((0, y * ss), txt, font=(p_req if genre == "q" else p_txt), fill=(124, 124, 132, 255))
    return img.resize((larg // 2, hh // 2), Image.LANCZOS)


def reveler(dern, aff, k, haut_total):
    """Apparition douce : hauteur visible, ligne en cours (bande + bord de l'effacement), coupe du reste."""
    if dern is None:
        return haut_total, None, None
    lignes, starts, y0 = dern["lignes"], dern["starts"], dern["y0"]
    n = sum(1 for s in starts if aff - s > 0)
    if n == 0:
        return y0 - 6, y0 * k, None
    j = n - 1
    r = aff - starts[j]
    txt = lignes[j]
    m = int(r)
    p = police_cache(15 * 2 * k)
    a = p.getlength(txt[:m])
    b = p.getlength(txt[:m + 1]) if m < len(txt) else a
    edge = (a + (r - m) * (b - a)) / 2 if r < len(txt) + 1 else 1e9
    bande = ((y0 + j * CARTE_LIGNE) * k, (y0 + (j + 1) * CARTE_LIGNE) * k, edge)
    return y0 + n * CARTE_LIGNE, (y0 + (j + 1) * CARTE_LIGNE) * k, bande


def vue_fil(couche, scroll, vh, k, coupe, bande, defile):
    W = couche.size[0]
    y0, Hh = round(scroll * k), max(2, round(vh * k))
    v = couche.crop((0, y0, W, y0 + Hh))
    a = np.asarray(v.split()[3], dtype=np.float32)
    ys = np.arange(y0, y0 + Hh, dtype=np.float32)
    if coupe is not None:
        a = a * (ys < coupe)[:, None]
    if bande is not None and bande[2] < 1e8:
        b0, b1, edge = bande
        lig = ((ys >= b0) & (ys < b1))[:, None]
        xs = np.arange(W, dtype=np.float32)[None, :]
        rampe = np.clip((edge - xs) / (3.0 * k), 0, 1)       # bord net : plus de fondu sur la ligne qui s'ecrit
        a = a * np.where(lig, rampe, 1.0)
    f = 4 * k                                           # plus de grand fondu en haut et en bas : le texte reste lisible
    idx = np.arange(Hh, dtype=np.float32)
    bord = np.ones(Hh, np.float32)
    if defile[0]:
        bord = np.minimum(bord, np.clip(idx / f, 0, 1))
    if defile[1]:
        bord = np.minimum(bord, np.clip((Hh - 1 - idx) / f, 0, 1))
    a = a * bord[:, None]
    v = v.copy()
    v.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L"))
    return v


def icone_img(nom, px, couleur, alpha=1.0):
    cle = (nom, px, couleur, round(alpha, 2))
    if cle in _icones:
        return _icones[cle]
    g = 4
    s = px * g
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = couleur + (round(255 * alpha),)
    w = max(2, round(1.7 * g * px / 18))
    if nom == "copier":
        a, b = s * 0.28, s * 0.70
        d.rounded_rectangle((a - s * .08, a - s * .08 - 0, b - s * .08, b - s * .08), radius=s * .09, outline=c, width=w)
        d.rounded_rectangle((a + s * .1, a + s * .1, b + s * .1, b + s * .1), radius=s * .09, outline=c, width=w)
    elif nom == "regen":
        d.arc((s * .22, s * .22, s * .78, s * .78), 35, 320, fill=c, width=w)
        x, y = s * .5 + s * .28 * math.cos(math.radians(320)), s * .5 + s * .28 * math.sin(math.radians(320))
        d.polygon([(x - s * .05, y - s * .16), (x + s * .16, y - s * .02), (x - s * .06, y + s * .08)], fill=c)
    elif nom == "liste":
        for yy in (.30, .50, .70):
            d.line([(s * .22, s * yy), (s * .78, s * yy)], fill=c, width=w)
    elif nom == "ok":
        d.line([(s * .25, s * .53), (s * .43, s * .70), (s * .76, s * .32)], fill=c, width=w + 1, joint="curve")
    elif nom == "agrandir":                     # chevron vers le bas : tout afficher
        d.line([(s * .28, s * .40), (s * .5, s * .62), (s * .72, s * .40)], fill=c, width=w, joint="curve")
    elif nom == "reduire":                      # chevron vers le haut : replier
        d.line([(s * .28, s * .62), (s * .5, s * .40), (s * .72, s * .62)], fill=c, width=w, joint="curve")
    elif nom == "fermer":
        d.line([(s * .3, s * .3), (s * .7, s * .7)], fill=c, width=w)
        d.line([(s * .7, s * .3), (s * .3, s * .7)], fill=c, width=w)
    im = im.resize((px, px), Image.LANCZOS)
    if len(_icones) > 80:
        _icones.clear()
    _icones[cle] = im
    return im


_gris_cache = {}
_forme_cache = {}


def _grille_gris(n_haut=16, n_larg=24):
    """Luminance et lobes lumineux sur une grille grossiere (agrandie en douceur ensuite)."""
    cle = (n_larg, n_haut)
    if cle not in _gris_cache:
        yy, xx = np.mgrid[0:n_haut, 0:n_larg].astype(np.float32)
        ang = (np.arctan2((yy + 0.5) / n_haut - 0.5, (xx + 0.5) / n_larg - 0.5) / (2 * np.pi) + 0.5).astype(np.float32)
        _gris_cache[cle] = ang
    return _gris_cache[cle]


def carte(cw, ch, rayon, contenu, vis_texte, lueur, rot, k, pos_contenu=None):
    """Carte noire tres arrondie, halo blanc doux qui respire. cw/ch/rayon en pixels physiques.
    Tout est calcule avec la distance a la forme (aucun flou) : une image en quelques millisecondes."""
    cw, ch = max(4, int(cw)), max(4, int(ch))
    m = round(34 * k)
    W, H = cw + 2 * m, ch + 2 * m
    rayon = max(1.0, min(rayon, ch / 2, cw / 2))
    cle = (W, H, round(rayon, 1), round(k, 2))
    if _forme_cache.get("cle") != cle:
        xs = (np.arange(W, dtype=np.float32) + 0.5 - W / 2)[None, :]
        ys = (np.arange(H, dtype=np.float32) + 0.5 - H / 2)[:, None]
        bx, by = cw / 2 - rayon, ch / 2 - rayon
        qx, qy = np.abs(xs) - bx, np.abs(ys) - by
        d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rayon
        forme = np.clip(0.5 - d, 0, 1)
        ep = max(1.6, 2.2 * k)
        lis = np.clip(0.5 - (np.abs(d + ep / 2) - ep / 2), 0, 1)
        d2 = d[::2, ::2]
        haut = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        base = 15 + 7 * (1 - haut)
        a_fond = forme * 0.97
        reflet = lis * (haut < 0.5) * (1 - haut * 2) ** 2 * 0.16
        dehors = np.exp(-np.maximum(d2, 0) / (9.0 * k)) * (d2 > -0.5)
        dedans = np.exp(np.minimum(d2, 0) / (7.0 * k)) * (d2 <= -0.5)
        halo2 = (dehors * 0.55 + dedans * 0.30).astype(np.float32)
        _forme_cache.clear()
        _forme_cache.update(cle=cle, forme=forme, lis=lis, halo2=halo2, base=base, a_fond=a_fond, reflet=reflet)
    c = _forme_cache
    forme, lis, halo2, base, a_fond, reflet = c["forme"], c["lis"], c["halo2"], c["base"], c["a_fond"], c["reflet"]
    h2, w2 = halo2.shape
    gh, gw = 16, 24
    ang = _grille_gris(gh, gw)
    lobes = (0.55 + 0.45 * np.sin(2 * np.pi * (ang * 2 - rot * 1.2))).astype(np.float32)
    lum = (190 + 60 * np.sin(2 * np.pi * (ang - rot * 0.6))).astype(np.float32)
    def agrandir(a, taille):
        return np.asarray(Image.fromarray(a, "F").resize(taille, Image.BILINEAR), dtype=np.float32)
    halo = agrandir(np.ascontiguousarray(halo2 * agrandir(lobes, (w2, h2))), (W, H))
    lumi = agrandir(lum, (W, H))
    a_glow = np.clip(halo * lueur + lis * (0.16 + 0.42 * lueur), 0, 1)
    out_a = np.clip(a_fond + a_glow * (1 - a_fond) + reflet, 0, 1)
    prem = base * a_fond * (1 - a_glow) + lumi * a_glow + reflet * 255.0
    g = np.clip(prem / np.maximum(out_a, 1e-3), 0, 255)
    sortie = np.empty((H, W, 4), np.uint8)
    tn = np.array(TEINTE_AGENT, np.float32) / max(TEINTE_AGENT)
    wt = np.clip(a_glow * 1.6, 0, 1)
    for ci in range(3):
        sortie[..., ci] = np.clip(g * (1 + wt * (tn[ci] - 1)), 0, 255)
    sortie[..., 3] = out_a * 255.0
    img = Image.fromarray(sortie, "RGBA")
    if contenu is not None and vis_texte > 0.02:
        t = contenu
        px, py = pos_contenu or (CARTE_PAD, CARTE_HAUT)
        dx, dy = m + round(px * k), m + round(py * k)
        ta = np.asarray(t.split()[3], dtype=np.float32) * vis_texte
        reg = forme[dy:dy + ta.shape[0], dx:dx + ta.shape[1]]
        if reg.shape == ta.shape:
            ta = ta * reg
        else:
            ta = ta[:reg.shape[0], :reg.shape[1]] * reg
        t2 = t.crop((0, 0, ta.shape[1], ta.shape[0]))
        t2.putalpha(Image.fromarray(np.clip(ta, 0, 255).astype(np.uint8), "L"))
        img.alpha_composite(t2, (dx, dy))
    return img, m


DET_L = 340          # largeur de la bulle de details (px logiques)
DET_PAD = 14
DET_TETE = 36
DET_VMAX = 380
DET_ENTETE = 46      # hauteur d'une ligne repliee
DET_SEC = ("Reasoning", "Web search", "Page", "Screenshot", "Tool")


def det_lignes(t, largeur, police, ss):
    """Contenu depliable d'un echange : raisonnement, recherches, pages lues, outils."""
    lignes = []

    def ajouter(genre, texte):
        for i, ligne in enumerate(decouper(texte, police, largeur)):
            lignes.append((genre, ligne))

    if t.get("pensee"):
        lignes.append(("sec", "REASONING"))
        ajouter("pensee", t["pensee"][-1200:])
    for ev in t.get("details", []):
        genre = ev.get("type")
        if genre == "search":
            lignes.append(("sec", "WEB SEARCH"))
            ajouter("lien", "“" + ev.get("titre", "") + "”")
            for titre, href in ev.get("liens", [])[:5]:
                hote = (urllib.parse.urlparse(href).hostname or "").replace("www.", "")
                ajouter("txt", "• " + (titre or hote)[:70] + (f"  ·  {hote}" if hote else ""))
        elif genre == "look":
            lignes.append(("sec", "PAGE"))
            ajouter("lien", ev.get("titre", ""))
            ajouter("txt", (ev.get("texte", "").split("\n", 1)[-1])[:240])
        elif genre == "vision":
            lignes.append(("sec", "WHAT IT SAW"))
            ajouter("txt", ev.get("texte", "")[:300])
        else:
            lignes.append(("sec", "TOOL"))
            ajouter("lien", ev.get("titre", ""))
            if ev.get("texte"):
                ajouter("txt", ev["texte"][:260])
    if not lignes:
        lignes.append(("txt", "Answered directly, no tools used." if t.get("final") else "Working…"))
    return lignes[:46]


def det_rendre_tour(t, k):
    """(entete, corps, hauteur_corps) en images RGBA a l'echelle k. Mis en cache dans l'echange."""
    ss = 2 * k
    cle = (t["q"], t["r"][:90], t.get("statut", ""), len(t.get("details", [])), len(t.get("pensee", "")) // 25, t.get("final"))
    c = t.get("_det")
    if c and c[0] == cle:
        return c[1], c[2], c[3]
    lw = DET_L - 2 * DET_PAD
    p_t, p_s = police_cache(13 * ss), police_cache(11.5 * ss)
    hd = Image.new("RGBA", (round(lw * ss), round(DET_ENTETE * ss)), (0, 0, 0, 0))
    d = ImageDraw.Draw(hd)
    d.text((18 * ss, 5 * ss), coupe_ligne(t["q"], p_t, (lw - 18) * ss), font=p_t, fill=(244, 244, 247, 255))
    apercu = (t["r"] or t.get("statut") or "…").replace("\n", " ")
    d.text((18 * ss, 25 * ss), coupe_ligne(apercu, p_s, (lw - 18) * ss), font=p_s, fill=(128, 128, 136, 255))
    entete = hd.resize((round(lw * k), round(DET_ENTETE * k)), Image.LANCZOS)
    lignes = det_lignes(t, (lw - 18) * ss, p_s, ss)
    h = len(lignes) * 15 + 10
    cb = Image.new("RGBA", (round(lw * ss), round(h * ss)), (0, 0, 0, 0))
    d = ImageDraw.Draw(cb)
    y = 4
    for genre, txt in lignes:
        if genre == "sec":
            y += 4 if y > 4 else 0
            d.text((18 * ss, y * ss), txt, font=police_cache(9.5 * ss), fill=(150, 150, 158, 255))
            y += 13
            continue
        coul = {"pensee": (170, 170, 178, 255), "lien": (232, 232, 238, 255)}.get(genre, (150, 150, 158, 255))
        d.text((18 * ss, y * ss), txt, font=p_s, fill=coul)
        y += 15
    h = y + 8
    corps = cb.crop((0, 0, cb.size[0], round(h * ss))).resize((round(lw * k), round(h * k)), Image.LANCZOS)
    t["_det"] = (cle, entete, corps, h)
    return entete, corps, h


def det_chevron(px, anim):
    """Petit chevron qui pivote de > a v."""
    g = 4
    s = px * g
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(im).line([(s * .36, s * .22), (s * .64, s * .5), (s * .36, s * .78)], fill=(150, 150, 158, 255), width=max(2, s // 7), joint="curve")
    im = im.rotate(-90 * anim, resample=Image.BICUBIC)
    return im.resize((px, px), Image.LANCZOS)


def det_composer(tours, k):
    """Toute la colonne (entetes + corps animes). Retourne (image, hauteur_logique, [(echange, y_logique)])."""
    lw = DET_L - 2 * DET_PAD
    rendus = [(t, det_rendre_tour(t, k)) for t in tours]
    total = sum(DET_ENTETE + r[2] * t.get("anim", 0.0) + 6 for t, r in rendus)
    img = Image.new("RGBA", (round(lw * k), max(2, round(total * k))), (0, 0, 0, 0))
    pos, y = [], 0.0
    px = round(12 * k)
    for t, (entete, corps, h) in rendus:
        a = t.get("anim", 0.0)
        img.alpha_composite(entete, (0, round(y * k)))
        img.alpha_composite(det_chevron(px, a), (0, round((y + 7) * k)))
        pos.append((t, y))
        y += DET_ENTETE
        hh = round(h * a * k)
        if hh > 1:
            part = corps.crop((0, 0, corps.size[0], min(corps.size[1], hh)))
            if a < 0.98:
                part.putalpha(part.split()[3].point(lambda v: int(v * a)))
            img.alpha_composite(part, (0, round(y * k)))
        y += h * a + 6
    return img, total, pos


def icone_tray():
    try:
        return Image.open(DOSSIER / "logo.png").convert("RGBA").resize((128, 128), Image.LANCZOS)
    except OSError:
        pass
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 124, 124), fill=(28, 28, 30, 255))
    d.rounded_rectangle((48, 24, 80, 70), radius=16, fill=(255, 255, 255, 255))
    d.arc((36, 44, 92, 90), 0, 180, fill=(255, 255, 255, 255), width=6)
    d.line((64, 90, 64, 104), fill=(255, 255, 255, 255), width=6)
    return img


def echelle_ecran():
    if sys.platform != "win32":
        return 1.0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        return ctypes.windll.user32.GetDpiForSystem() / 96
    except Exception:
        return 1.0


def bgra_premultiplie(img):
    arr = np.asarray(img.convert("RGBA")).astype(np.uint32)
    a = arr[..., 3]
    bgra = np.stack([arr[..., 2] * a // 255, arr[..., 1] * a // 255, arr[..., 0] * a // 255, a], axis=-1)
    return np.ascontiguousarray(bgra.astype(np.uint8)).tobytes()


if sys.platform == "win32":
    from ctypes import wintypes

    class _EnteteBmp(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    class _Melange(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _g32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _u32.GetDC.restype, _u32.GetDC.argtypes = wintypes.HDC, [wintypes.HWND]
    _u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _u32.GetParent.restype, _u32.GetParent.argtypes = wintypes.HWND, [wintypes.HWND]
    _u32.GetWindowLongW.restype, _u32.GetWindowLongW.argtypes = wintypes.LONG, [wintypes.HWND, ctypes.c_int]
    _u32.SetWindowLongW.restype = wintypes.LONG
    _u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    _u32.UpdateLayeredWindow.restype = wintypes.BOOL
    _u32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                         ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                         ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                         ctypes.POINTER(_Melange), wintypes.DWORD]
    _g32.CreateCompatibleDC.restype, _g32.CreateCompatibleDC.argtypes = wintypes.HDC, [wintypes.HDC]
    _g32.CreateDIBSection.restype = wintypes.HBITMAP
    _g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                      ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    _g32.SelectObject.restype, _g32.SelectObject.argtypes = wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]
    _g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _g32.DeleteDC.argtypes = [wintypes.HDC]


_PAUSE = ([(-5.6, -6.5), (-5.6, 6.5), (-2.0, 6.5), (-2.0, -6.5)],
          [(2.0, -6.5), (2.0, 6.5), (5.6, 6.5), (5.6, -6.5)])
_LECTURE = ([(-3.5, -7.0), (-3.5, 7.0), (2.0, 3.5), (2.0, -3.5)],
            [(2.0, -3.5), (2.0, 3.5), (7.5, 0.0), (7.5, 0.0)])


def bouton(m, k, vis):
    """m = 0 : deux barres (pause), m = 1 : triangle (lecture). Les formes se transforment en continu."""
    N = 38 * S
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    r = np.sqrt((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2)
    t = np.clip((r - 0.15) / 0.85, 0, 1)
    t = t * t * (3 - 2 * t)
    centre = np.array((30, 30, 34), dtype=np.float32)
    bord = np.array(PILULE[:3], dtype=np.float32)
    rgb = centre[None, None, :] * (1 - t[..., None]) + bord[None, None, :] * t[..., None]
    forme = Image.new("L", (N, N), 0)
    ImageDraw.Draw(forme).ellipse((0, 0, N - 1, N - 1), fill=255)
    img = Image.fromarray(np.dstack([rgb.astype(np.uint8), np.full((N, N), 255, np.uint8)]), "RGBA")
    img.putalpha(forme)
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, N - 1, N - 1), outline=BORD, width=S)
    c = N / 2
    icone = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    di = ImageDraw.Draw(icone)
    e = m
    couleur = melange(BLANC, vis)
    for p0, p1 in zip(_PAUSE, _LECTURE):
        pts = [(c + (a[0] + (b[0] - a[0]) * e) * S, c + (a[1] + (b[1] - a[1]) * e) * S) for a, b in zip(p0, p1)]
        di.polygon(pts, fill=couleur)
        di.line(pts + [pts[0]], fill=couleur, width=int(1.8 * S), joint="curve")
    lueur = icone.filter(ImageFilter.GaussianBlur(2.2 * S))
    lueur.putalpha(lueur.split()[3].point(lambda v: int(v * 0.45)))
    img.alpha_composite(lueur)
    img.alpha_composite(icone)
    img.putalpha(Image.fromarray(np.minimum(np.array(img.split()[3]), np.array(forme)), "L"))
    taille = max(2, round(38 * k))
    return img.resize((taille, taille), Image.LANCZOS)


# ---- icones SVG (style Lucide, viewBox 24x24, traits arrondis) -------------------------------------------
SVG_ICONES = {
    # fichiers microphone.svg / send.svg / delete.svg de l'utilisateur (SVG Repo)
    "mic": {"vb": 24, "trait": 2.0, "d": (
        "M20 12V13C20 17.4183 16.4183 21 12 21C7.58172 21 4 17.4183 4 13V12M12 17C9.79086 17 8 15.2091 8 13V7C8 4.79086 "
        "9.79086 3 12 3C14.2091 3 16 4.79086 16 7V13C16 15.2091 14.2091 17 12 17Z",)},
    "texte_sel": {"vb": 24, "remplir": True, "d": ("M9.95197 6.25001C9.52212 6.24994 9.12024 6.24987 8.79192 6.29892C8.42103 6.35433 8.04 6.48531 7.73543 6.82372C7.44103 7.15083 7.3371 7.54062 7.29205 7.91295C7.24993 8.26097 7.24997 8.69239 7.25 9.17955L7.25 9.75001C7.25 10.1642 7.58579 10.5 8 10.5C8.41422 10.5 8.75 10.1642 8.75 9.75001V9.22223C8.75 8.67932 8.7513 8.34012 8.78118 8.09314C8.79521 7.97726 8.81273 7.91049 8.8269 7.87222C8.83886 7.83994 8.8474 7.83047 8.85023 7.82732L8.85104 7.82638C8.85241 7.82474 8.85341 7.82354 8.86242 7.81941C8.87905 7.81181 8.92169 7.79618 9.01354 7.78246C9.21765 7.75197 9.50512 7.75001 10 7.75001H11.25V16.25H9.5C9.08579 16.25 8.75 16.5858 8.75 17C8.75 17.4142 9.08579 17.75 9.5 17.75H15C15.4142 17.75 15.75 17.4142 15.75 17C15.75 16.5858 15.4142 16.25 15 16.25H12.75V7.75001H14C14.4949 7.75001 14.7824 7.75197 14.9865 7.78246C15.0783 7.79618 15.121 7.81181 15.1376 7.81941C15.1466 7.82354 15.1476 7.82474 15.149 7.82638L15.1496 7.82717C15.1525 7.83032 15.1612 7.83994 15.1731 7.87222C15.1873 7.91049 15.2048 7.97726 15.2188 8.09314C15.2487 8.34012 15.25 8.67932 15.25 9.22223V9.75001C15.25 10.1642 15.5858 10.5 16 10.5C16.4142 10.5 16.75 10.1642 16.75 9.75001L16.75 9.17954C16.75 8.69239 16.7501 8.26096 16.708 7.91295C16.6629 7.54062 16.559 7.15083 16.2646 6.82372C15.96 6.48531 15.579 6.35433 15.2081 6.29892C14.8798 6.24987 14.4779 6.24994 14.048 6.25001H9.95197Z",)},
    "poubelle": {"vb": 24, "trait": 2.0, "d": (
        "M4 7H20",
        "M6 10L7.70141 19.3578C7.87432 20.3088 8.70258 21 9.66915 21H14.3308C15.2974 21 16.1257 20.3087 16.2986 19.3578L18 10",
        "M9 5C9 3.89543 9.89543 3 11 3H13C14.1046 3 15 3.89543 15 5V7H9V5Z")},
    "envoi": {"vb": 32, "remplir": True, "decal": (-360.0, -1087.0), "d": (
        "M376,1117 C368.268,1117 362,1110.73 362,1103 C362,1095.27 368.268,1089 376,1089 C383.732,1089 390,1095.27 390,1103 "
        "C390,1110.73 383.732,1117 376,1117 L376,1117 Z M376,1087 C367.163,1087 360,1094.16 360,1103 C360,1111.84 367.163,1119 "
        "376,1119 C384.837,1119 392,1111.84 392,1103 C392,1094.16 384.837,1087 376,1087 L376,1087 Z M376.879,1096.46 "
        "C376.639,1096.22 376.311,1096.15 376,1096.21 C375.689,1096.15 375.361,1096.22 375.121,1096.46 L369.465,1102.12 "
        "C369.074,1102.51 369.074,1103.14 369.465,1103.54 C369.854,1103.93 370.488,1103.93 370.879,1103.54 L375,1099.41 "
        "L375,1110 C375,1110.55 375.447,1111 376,1111 C376.553,1111 377,1110.55 377,1110 L377,1099.41 L381.121,1103.54 "
        "C381.512,1103.93 382.145,1103.93 382.535,1103.54 C382.926,1103.14 382.926,1102.51 382.535,1102.12 L376.879,1096.46 "
        "L376.879,1096.46 Z",)},
}


def _svg_points(d):
    """Lit un chemin SVG (M L H V C A Z, absolu ou relatif) et rend des listes de points."""
    import re
    jetons = re.findall(r"[MmLlHhVvCcAaZz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    i, cmd, x, y, debut = 0, None, 0.0, 0.0, (0.0, 0.0)
    chemins, cur = [], []

    def nb(n):
        nonlocal i
        v = [float(t) for t in jetons[i:i + n]]
        i += n
        return v

    while i < len(jetons):
        if jetons[i].isalpha():
            cmd = jetons[i]
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append(debut)
                    chemins.append(cur)
                    cur = []
                x, y = debut
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            a, b = nb(2)
            x, y = (x + a, y + b) if rel else (a, b)
            if cur:
                chemins.append(cur)
            cur, debut = [(x, y)], (x, y)
            cmd = "l" if rel else "L"
        elif c == "L":
            a, b = nb(2)
            x, y = (x + a, y + b) if rel else (a, b)
            cur.append((x, y))
        elif c == "H":
            a, = nb(1)
            x = x + a if rel else a
            cur.append((x, y))
        elif c == "V":
            a, = nb(1)
            y = y + a if rel else a
            cur.append((x, y))
        elif c == "C":
            v = nb(6)
            if rel:
                v = [v[0] + x, v[1] + y, v[2] + x, v[3] + y, v[4] + x, v[5] + y]
            for k in range(1, 13):
                t = k / 12
                u = 1 - t
                cur.append((u ** 3 * x + 3 * u * u * t * v[0] + 3 * u * t * t * v[2] + t ** 3 * v[4],
                            u ** 3 * y + 3 * u * u * t * v[1] + 3 * u * t * t * v[3] + t ** 3 * v[5]))
            x, y = v[4], v[5]
        elif c == "A":
            rx, ry, rot, fa, fs, ex, ey = nb(7)
            if rel:
                ex, ey = ex + x, ey + y
            cur.extend(_svg_arc(x, y, rx, ry, rot, int(fa), int(fs), ex, ey))
            x, y = ex, ey
    if cur:
        chemins.append(cur)
    return chemins


def _svg_arc(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    ph = math.radians(phi)
    c, s_ = math.cos(ph), math.sin(ph)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = c * dx + s_ * dy, -s_ * dx + c * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = c * cxp - s_ * cyp + (x1 + x2) / 2, s_ * cxp + c * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    pts = []
    for k in range(1, 17):
        t = t1 + dt * k / 16
        px, py = rx * math.cos(t), ry * math.sin(t)
        pts.append((c * px - s_ * py + cx, s_ * px + c * py + cy))
    return pts


_cache_svg = {}


def icone_svg(nom, px, couleur, epaisseur=None, echelle=8):
    """Dessine une icone SVG a la taille px (traits arrondis ou formes pleines, regle pair-impair), avec lissage."""
    cle = (nom, px, couleur, epaisseur)
    if cle in _cache_svg:
        return _cache_svg[cle]
    if len(_cache_svg) > 80:
        _cache_svg.clear()
    _cache_svg[cle] = out = _icone_svg(nom, px, couleur, epaisseur, echelle)
    return out


def _icone_svg(nom, px, couleur, epaisseur, echelle):
    spec = SVG_ICONES[nom]
    N = px * echelle
    u = N / float(spec["vb"])
    dx, dy = spec.get("decal", (0.0, 0.0))
    chemins = [[[((x + dx) * u, (y + dy) * u) for x, y in pts] for pts in _svg_points(d)] for d in spec["d"]]
    if spec.get("remplir"):
        masque = np.zeros((N, N), bool)
        for sous in chemins:
            for pts in sous:
                m = Image.new("L", (N, N), 0)
                ImageDraw.Draw(m).polygon(pts, fill=255)
                masque ^= np.asarray(m) > 127
        im = Image.new("RGBA", (N, N), couleur + (255,))
        im.putalpha(Image.fromarray((masque * 255).astype(np.uint8), "L"))
        return im.resize((px, px), Image.LANCZOS)
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(1, round((epaisseur or spec.get("trait", 2.0)) * u))
    for sous in chemins:
        for xy in sous:
            if len(xy) > 1:
                d.line(xy, fill=couleur + (255,), width=w, joint="curve")
            for a_, b_ in (xy[0], xy[-1]):
                d.ellipse((a_ - w / 2, b_ - w / 2, a_ + w / 2, b_ + w / 2), fill=couleur + (255,))
    return im.resize((px, px), Image.LANCZOS)


_cache_btn = {}


def bouton_icone(nom, k, vis, survol=False, actif=True):
    """Boutons ronds de la bulle de texte, meme style que pause / poubelle : micro (gauche) et envoi (droite)."""
    cle = (nom, round(k, 2), round(vis, 2), survol, actif)
    if cle in _cache_btn:
        return _cache_btn[cle]
    N = 38 * S
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    r = np.sqrt((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2)
    t = np.clip((r - 0.15) / 0.85, 0, 1)
    t = t * t * (3 - 2 * t)
    centre = np.array((46, 46, 52) if survol else (30, 30, 34), dtype=np.float32)
    bord = np.array(PILULE[:3], dtype=np.float32)
    rgb = centre[None, None, :] * (1 - t[..., None]) + bord[None, None, :] * t[..., None]
    forme = Image.new("L", (N, N), 0)
    ImageDraw.Draw(forme).ellipse((0, 0, N - 1, N - 1), fill=255)
    img = Image.fromarray(np.dstack([rgb.astype(np.uint8), np.full((N, N), 255, np.uint8)]), "RGBA")
    img.putalpha(forme)
    ImageDraw.Draw(img).ellipse((0, 0, N - 1, N - 1), outline=BORD, width=S)
    c = N / 2
    icone = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    di = ImageDraw.Draw(icone)
    if nom == "envoi":
        couleur = melange((255, 255, 255) if survol else (245, 245, 247), vis) if actif else melange((92, 92, 98), vis)
        glyphe = icone_svg("envoi", round(N * 0.92), couleur)       # send.svg est deja un rond avec une fleche
    else:
        couleur = melange(BLANC, vis)
        glyphe = icone_svg("mic", 18 * S, couleur)
    icone.alpha_composite(glyphe, (int(c - glyphe.size[0] / 2), int(c - glyphe.size[1] / 2)))
    img.alpha_composite(icone)
    img.putalpha(Image.fromarray(np.minimum(np.array(img.split()[3]), np.array(forme)), "L"))
    taille = max(2, round(38 * k))
    out = img.resize((taille, taille), Image.LANCZOS)
    if len(_cache_btn) > 60:
        _cache_btn.clear()
    _cache_btn[cle] = out
    return out


def bouton_poubelle(k, vis, nom="poubelle"):
    """Bouton rond a gauche : supprime l'enregistrement en cours (meme style que le bouton pause)."""
    N = 38 * S
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    r = np.sqrt((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2)
    t = np.clip((r - 0.15) / 0.85, 0, 1)
    t = t * t * (3 - 2 * t)
    centre = np.array((30, 30, 34), dtype=np.float32)
    bord = np.array(PILULE[:3], dtype=np.float32)
    rgb = centre[None, None, :] * (1 - t[..., None]) + bord[None, None, :] * t[..., None]
    forme = Image.new("L", (N, N), 0)
    ImageDraw.Draw(forme).ellipse((0, 0, N - 1, N - 1), fill=255)
    img = Image.fromarray(np.dstack([rgb.astype(np.uint8), np.full((N, N), 255, np.uint8)]), "RGBA")
    img.putalpha(forme)
    ImageDraw.Draw(img).ellipse((0, 0, N - 1, N - 1), outline=BORD, width=S)
    c = N / 2
    icone = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    di = ImageDraw.Draw(icone)
    couleur = melange(BLANC, vis)
    w = int(1.8 * S)

    def trait(pts):
        di.line([(c + x * S, c + y * S) for x, y in pts], fill=couleur, width=w, joint="curve")
        for x, y in (pts[0], pts[-1]):
            di.ellipse((c + x * S - w / 2, c + y * S - w / 2, c + x * S + w / 2, c + y * S + w / 2), fill=couleur)

    glyphe = icone_svg(nom, 18 * S, couleur)
    icone.alpha_composite(glyphe, (int(c - glyphe.size[0] / 2), int(c - glyphe.size[1] / 2)))
    lueur = icone.filter(ImageFilter.GaussianBlur(2.2 * S))
    lueur.putalpha(lueur.split()[3].point(lambda v: int(v * 0.45)))
    img.alpha_composite(lueur)
    img.alpha_composite(icone)
    img.putalpha(Image.fromarray(np.minimum(np.array(img.split()[3]), np.array(forme)), "L"))
    taille = max(2, round(38 * k))
    return img.resize((taille, taille), Image.LANCZOS)


class Calque:
    def __init__(self, root):
        self.root = root
        self.hwnd = None
        self.erreur_loguee = False

    def preparer(self):
        if sys.platform != "win32":
            return
        wid = self.root.winfo_id()
        self.hwnd = _u32.GetParent(wid) or wid
        style = _u32.GetWindowLongW(self.hwnd, -20)
        _u32.SetWindowLongW(self.hwnd, -20, style | 0x80000 | 0x08000000 | 0x80)

    def remonter(self):
        """Replace la fenetre au-dessus des autres (Windows peut l'enfouir : barre des taches, menu Demarrer, plein ecran...) et la remontre si elle a ete masquee."""
        if sys.platform != "win32" or not self.hwnd:
            return
        h = ctypes.c_void_p(self.hwnd)
        if not _u32.IsWindowVisible(h):
            _u32.ShowWindow(h, 4)                      # SW_SHOWNOACTIVATE
        _u32.SetWindowPos(h, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)

    def deplacer(self, x, y):
        """Deplace la fenetre sans redessiner son image : le glisser reste fluide (le dessin, lui, coute 30 a 40 ms)."""
        if sys.platform != "win32" or not self.hwnd:
            return
        _u32.SetWindowPos(ctypes.c_void_p(self.hwnd), None, int(x), int(y), 0, 0, 0x0001 | 0x0004 | 0x0010)

    def poser(self, img, x, y, opacite):
        if sys.platform != "win32" or not self.hwnd:
            return
        w, h = img.size
        donnees = bgra_premultiplie(img)
        ecran = _u32.GetDC(None)
        memoire = _g32.CreateCompatibleDC(ecran)
        entete = _EnteteBmp(ctypes.sizeof(_EnteteBmp), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bitmap = _g32.CreateDIBSection(ecran, ctypes.byref(entete), 0, ctypes.byref(bits), None, 0)
        try:
            ctypes.memmove(bits, donnees, len(donnees))
            ancien = _g32.SelectObject(memoire, bitmap)
            melange = _Melange(0, 0, max(0, min(255, int(255 * opacite))), 1)
            ok = _u32.UpdateLayeredWindow(self.hwnd, ecran, ctypes.byref(wintypes.POINT(x, y)),
                                          ctypes.byref(wintypes.SIZE(w, h)), memoire,
                                          ctypes.byref(wintypes.POINT(0, 0)), 0,
                                          ctypes.byref(melange), 2)
            if not ok and not self.erreur_loguee:
                self.erreur_loguee = True
                log(f"UpdateLayeredWindow failed (code {ctypes.get_last_error()})")
            _g32.SelectObject(memoire, ancien)
        finally:
            _g32.DeleteObject(bitmap)
            _g32.DeleteDC(memoire)
            _u32.ReleaseDC(None, ecran)


class Molette:
    """Capte la molette seulement quand le curseur est au-dessus de la carte de l'assistant."""

    def __init__(self, app):
        self.app = app
        if sys.platform == "win32":
            threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self):
        try:
            u = ctypes.WinDLL("user32", use_last_error=True)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            hook_t = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
            u.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_t, ctypes.c_void_p, ctypes.c_uint]
            u.SetWindowsHookExW.restype = ctypes.c_void_p
            u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
            u.CallNextHookEx.restype = ctypes.c_ssize_t
            k32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
            k32.GetModuleHandleW.restype = ctypes.c_void_p

            class Souris(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long), ("data", ctypes.c_uint),
                            ("flags", ctypes.c_uint), ("temps", ctypes.c_uint), ("extra", ctypes.c_size_t)]

            def rappel(code, wp, lp):
                try:
                    if code == 0 and wp == 0x020A:
                        m = Souris.from_address(lp)
                        for zone, attr in ((self.app.rect_carte, "molette"), (self.app.rect_details, "molette_d")):
                            if zone and zone[0] <= m.x <= zone[2] and zone[1] <= m.y <= zone[3]:
                                setattr(self.app, attr, getattr(self.app, attr) + ctypes.c_short((m.data >> 16) & 0xFFFF).value)
                                return 1
                except Exception:
                    pass
                return u.CallNextHookEx(None, code, wp, lp)

            self._cb = hook_t(rappel)
            if not u.SetWindowsHookExW(14, self._cb, k32.GetModuleHandleW(None), 0):
                log("wheel hook unavailable")
                return
            msg = wintypes.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        except Exception:
            log(traceback.format_exc())


class Ressort:
    def __init__(self, x):
        self.x = x
        self.v = 0.0

    def pas(self, cible, reponse, dt, amort=1.0):
        w = 2 * math.pi / reponse
        d = self.x - cible
        if amort >= 1.0:
            b = self.v + w * d
            e = math.exp(-w * dt)
            self.x = cible + (d + b * dt) * e
            self.v = (self.v - b * w * dt) * e
        else:
            a = amort * w
            wd = w * math.sqrt(1 - amort ** 2)
            sn0 = (self.v + a * d) / wd
            e = math.exp(-a * dt)
            cs, sn = math.cos(wd * dt), math.sin(wd * dt)
            self.x = cible + e * (d * cs + sn0 * sn)
            self.v = e * ((-a * d + wd * sn0) * cs + (-a * sn0 - wd * d) * sn)
        return self.x


def animations_actives():
    if sys.platform != "win32":
        return True
    try:
        ok = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(ok), 0)
        return bool(ok.value)
    except Exception:
        return True
