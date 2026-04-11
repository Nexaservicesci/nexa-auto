#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXA Services — Script d'automatisation Facebook (version Railway)
==================================================================
Ce script tourne 24h/24 sur Railway.app et publie automatiquement
tes posts planifiés sur ta page Facebook NEXA Services.

VARIABLES D'ENVIRONNEMENT À CONFIGURER SUR RAILWAY :
  PAGE_ID            → ton Page ID Facebook
  PAGE_ACCESS_TOKEN  → ton Page Access Token
  WA_NUMBER          → ton numéro WhatsApp (ex: +225 07 00 00 00 00)

FICHIERS NÉCESSAIRES DANS LE REPO GITHUB :
  nexa_auto_railway.py  ← ce fichier
  requirements.txt
  Procfile
  NEXA_sauvegarde.json  ← exporté depuis la plateforme NEXA
"""

import json
import os
import time
import logging
import requests
import schedule
from datetime import datetime, date
from pathlib import Path

# ═══════════════════════════════════════════════════════
#  CONFIGURATION — Lues depuis les variables Railway
# ═══════════════════════════════════════════════════════

PAGE_ID           = os.environ.get("PAGE_ID", "")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
WA_NUMBER         = os.environ.get("WA_NUMBER", "+225 07 00 00 00 00")
EXPORT_FILE       = os.environ.get("EXPORT_FILE", "NEXA_sauvegarde.json")
HEURES            = ["07:00", "12:00", "18:00", "20:00"]
FB_API            = "https://graph.facebook.com/v25.0"
POSTS_PUBLIES_FILE = "posts_publies.json"

# ═══════════════════════════════════════════════════════
#  LOGS — Affichés dans Railway Dashboard
# ═══════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("NEXA")

# ═══════════════════════════════════════════════════════
#  VÉRIFICATION DES VARIABLES AU DÉMARRAGE
# ═══════════════════════════════════════════════════════

def verifier_config():
    """Vérifie que les variables Railway sont bien renseignées."""
    erreurs = []
    if not PAGE_ID or PAGE_ID == "":
        erreurs.append("PAGE_ID manquant — ajoute-le dans Railway > Variables")
    if not PAGE_ACCESS_TOKEN or PAGE_ACCESS_TOKEN == "":
        erreurs.append("PAGE_ACCESS_TOKEN manquant — ajoute-le dans Railway > Variables")
    if erreurs:
        for e in erreurs:
            log.error(f"❌ {e}")
        return False
    log.info(f"✅ Variables Railway chargées — Page ID : {PAGE_ID[:8]}...")
    return True

# ═══════════════════════════════════════════════════════
#  FACEBOOK API
# ═══════════════════════════════════════════════════════

def test_connexion():
    """Vérifie que le token Facebook est valide."""
    url = f"{FB_API}/{PAGE_ID}"
    params = {"fields": "name,fan_count", "access_token": PAGE_ACCESS_TOKEN}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if "error" in data:
            log.error(f"❌ Token invalide : {data['error']['message']}")
            return False
        fans = data.get('fan_count', 0)
        log.info(f"✅ Connecté : {data.get('name')} — {fans} abonnés")
        return True
    except Exception as e:
        log.error(f"❌ Erreur connexion : {e}")
        return False


def publier_texte(texte):
    """Publie un post texte sur la page Facebook."""
    url = f"{FB_API}/{PAGE_ID}/feed"
    data = {"message": texte, "access_token": PAGE_ACCESS_TOKEN}
    try:
        r = requests.post(url, data=data, timeout=30)
        result = r.json()
        if "id" in result:
            log.info(f"✅ Post publié — ID Facebook : {result['id']}")
            return result["id"]
        else:
            msg = result.get('error', {}).get('message', 'Erreur inconnue')
            log.error(f"❌ Échec publication : {msg}")
            return None
    except Exception as e:
        log.error(f"❌ Erreur publication : {e}")
        return None


def publier_avec_photo(texte, url_photo_base64):
    """Publie un post avec une image encodée en base64."""
    import base64, tempfile
    url_api = f"{FB_API}/{PAGE_ID}/photos"
    try:
        # Décoder le base64 en fichier temporaire
        if url_photo_base64.startswith("data:"):
            header, data_b64 = url_photo_base64.split(",", 1)
        else:
            data_b64 = url_photo_base64
        img_data = base64.b64decode(data_b64)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img_data)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            files = {"source": ("photo.jpg", f, "image/jpeg")}
            data = {"message": texte, "access_token": PAGE_ACCESS_TOKEN}
            r = requests.post(url_api, files=files, data=data, timeout=60)
        os.unlink(tmp_path)
        result = r.json()
        if "id" in result:
            log.info(f"✅ Post avec photo publié — ID : {result['id']}")
            return result["id"]
        else:
            log.warning("⚠️ Upload photo échoué — publication sans photo")
            return publier_texte(texte)
    except Exception as e:
        log.error(f"❌ Erreur upload photo : {e}")
        return publier_texte(texte)


def repondre_messenger(sender_id, texte):
    """Envoie une réponse via Messenger."""
    url = f"{FB_API}/me/messages"
    data = {
        "recipient": {"id": sender_id},
        "message": {"text": texte},
        "access_token": PAGE_ACCESS_TOKEN
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        return "message_id" in r.json()
    except Exception as e:
        log.error(f"❌ Erreur Messenger : {e}")
        return False

# ═══════════════════════════════════════════════════════
#  GESTION DES POSTS PLANIFIÉS
# ═══════════════════════════════════════════════════════

POSTS_PUBLIES = set()


def charger_posts_publies():
    global POSTS_PUBLIES
    if os.path.exists(POSTS_PUBLIES_FILE):
        try:
            with open(POSTS_PUBLIES_FILE, "r", encoding="utf-8") as f:
                POSTS_PUBLIES = set(json.load(f))
        except Exception:
            POSTS_PUBLIES = set()
    log.info(f"📋 {len(POSTS_PUBLIES)} posts déjà publiés en mémoire")


def sauvegarder_posts_publies():
    with open(POSTS_PUBLIES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(POSTS_PUBLIES), f)


def charger_export():
    """Charge le fichier JSON exporté depuis la plateforme NEXA."""
    if not os.path.exists(EXPORT_FILE):
        log.warning(f"⚠️ Fichier {EXPORT_FILE} non trouvé — aucun post à publier")
        return None
    try:
        with open(EXPORT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        nb_biens = len(data.get("biens", []))
        nb_posts = len(data.get("scheduled", []))
        log.info(f"📂 Export chargé : {nb_biens} biens, {nb_posts} posts planifiés")
        return data
    except Exception as e:
        log.error(f"❌ Erreur lecture export : {e}")
        return None


def generer_texte(post, biens, page):
    """Génère le texte du post depuis les données du bien."""
    # Texte complet déjà disponible
    texte = post.get("text", "")
    if texte and not texte.endswith("…"):
        return texte

    # Reconstruire depuis les infos du bien
    bien_id = str(post.get("bienId", ""))
    bien = next((b for b in biens if str(b.get("id")) == bien_id), None)
    wa = page.get("wa", WA_NUMBER)
    ht = page.get("ht", "#NEXAServices #LocationAbidjan")
    type_post = post.get("type", "Disponibilité")

    if not bien:
        return f"📢 Nouveau post NEXA Services\n\n📲 Contactez-nous : {wa}\n\n{ht}"

    nom   = bien.get("name", "")
    zone  = bien.get("zone", "")
    prix  = bien.get("prix", "")
    equip = bien.get("equip", "")
    dispo = bien.get("dispo", "disponible")
    cat   = bien.get("cat", "appart")

    emojis = {"appart": "🏠", "villa": "🏡", "voiture": "🚗", "bureau": "🏢", "autre": "📦"}
    emoji = emojis.get(cat, "🏠")

    if type_post == "Disponibilité":
        texte = f"{emoji} {nom} est disponible !\n\n📍 {zone}\n💰 À partir de {prix} FCFA\n✅ {equip}\n\n📲 Réservation rapide sur WhatsApp :\n{wa}\n\n{ht}"
    elif type_post == "Promotion":
        texte = f"🔥 OFFRE SPÉCIALE — {nom}\n\n📍 {zone}\n💰 {prix} FCFA seulement !\n✅ {equip}\n\n⚡ Offre limitée ! Réservez vite :\n{wa}\n\n{ht}"
    elif type_post == "Présentation":
        texte = f"✨ Découvrez {nom}\n\n📍 {zone}\n💰 {prix} FCFA\n🛎️ {equip}\n\n📲 Informations et réservations :\n{wa}\n\n{ht}"
    elif type_post == "Weekend spécial":
        texte = f"🌟 Weekend parfait au {nom} !\n\n📍 {zone}\n💰 {prix} FCFA\n✅ {equip}\n\n📲 Disponible ce weekend — réservez :\n{wa}\n\n{ht}"
    else:
        texte = f"{emoji} {nom} — {zone}\n💰 {prix} FCFA\n\n📲 {wa}\n\n{ht}"

    return texte


def trouver_meilleure_photo(post, biens):
    """Trouve la meilleure photo optimisée pour ce post."""
    bien_id = str(post.get("bienId", ""))
    mids = post.get("mids", [])
    bien = next((b for b in biens if str(b.get("id")) == bien_id), None)
    if not bien:
        return None
    medias = bien.get("media", [])
    # Priorité aux médias sélectionnés dans le post
    if mids:
        for m in medias:
            if str(m.get("id")) in [str(mid) for mid in mids]:
                src = m.get("optimizedSrc") or m.get("src")
                if src and src.startswith("data:image"):
                    return src
    # Sinon premier média optimisé du bien
    for m in medias:
        if m.get("isOpt") and m.get("type") == "photo":
            src = m.get("optimizedSrc") or m.get("src")
            if src and src.startswith("data:image"):
                return src
    # Sinon premier média photo
    for m in medias:
        if m.get("type") == "photo":
            src = m.get("src")
            if src and src.startswith("data:image"):
                return src
    return None


def publier_posts_du_jour():
    """Publie tous les posts prévus pour aujourd'hui."""
    log.info("─" * 50)
    log.info("🚀 Vérification des posts à publier...")
    data = charger_export()
    if not data:
        return

    biens     = data.get("biens", [])
    page      = data.get("page", {})
    scheduled = data.get("scheduled", [])
    aujourdhui = date.today().isoformat()

    posts_jour = [p for p in scheduled if p.get("date") == aujourdhui]
    log.info(f"📅 {len(posts_jour)} post(s) prévu(s) pour aujourd'hui ({aujourdhui})")

    if not posts_jour:
        log.info("✅ Rien à publier aujourd'hui")
        return

    publies = 0
    for post in posts_jour:
        post_id = f"{post.get('date')}_{post.get('bienId')}_{post.get('type')}"
        if post_id in POSTS_PUBLIES:
            log.info(f"⏩ Déjà publié : {post.get('bienName')} / {post.get('type')}")
            continue

        texte = generer_texte(post, biens, page)
        photo = trouver_meilleure_photo(post, biens)

        log.info(f"📤 Publication : {post.get('bienName')} / {post.get('type')} {'📷' if photo else '📝'}")

        result = publier_avec_photo(texte, photo) if photo else publier_texte(texte)

        if result:
            POSTS_PUBLIES.add(post_id)
            sauvegarder_posts_publies()
            publies += 1
            if len(posts_jour) > 1:
                log.info("⏳ Pause 30 min avant le prochain post...")
                time.sleep(30 * 60)

    log.info(f"✅ {publies}/{len(posts_jour)} post(s) publié(s) aujourd'hui")

# ═══════════════════════════════════════════════════════
#  RÉPONSES AUTOMATIQUES MESSENGER
# ═══════════════════════════════════════════════════════

REPONSES = {
    "appartement": f"Bonjour 😊 Nous avons plusieurs appartements disponibles à Abidjan. Précisez votre quartier, dates et nombre de personnes → WhatsApp : {WA_NUMBER}",
    "appart":      f"Bonjour 😊 Nous avons plusieurs appartements disponibles. → WhatsApp : {WA_NUMBER}",
    "villa":       f"Bonjour 🏡 Nous proposons des villas avec piscine. Partagez vos dates → WhatsApp : {WA_NUMBER}",
    "piscine":     f"Bonjour 🏊 Nos villas avec piscine sont disponibles ! → WhatsApp : {WA_NUMBER}",
    "voiture":     f"Bonjour 🚗 Flotte de véhicules disponibles. Quelle période ? → WhatsApp : {WA_NUMBER}",
    "vehicle":     f"Bonjour 🚗 Flotte de véhicules disponibles. → WhatsApp : {WA_NUMBER}",
    "prix":        "Appartements dès 35 000 FCFA/nuit · Villas dès 80 000 FCFA/nuit · Voitures dès 25 000 FCFA/jour.",
    "tarif":       "Appartements dès 35 000 FCFA/nuit · Villas dès 80 000 FCFA/nuit · Voitures dès 25 000 FCFA/jour.",
    "combien":     "Appartements dès 35 000 FCFA/nuit · Villas dès 80 000 FCFA/nuit · Voitures dès 25 000 FCFA/jour.",
    "disponible":  f"Bonjour ! Précisez le type de bien, vos dates et le nombre de personnes → WhatsApp : {WA_NUMBER}",
    "reserv":      f"Bonjour ! Pour réserver, contactez-nous sur WhatsApp : {WA_NUMBER}",
    "merci":       "Merci pour votre confiance ! 🙏 Un avis sur notre page nous aide beaucoup. À bientôt !",
    "bonjour":     f"Bonjour ! 😊 Comment pouvons-nous vous aider ? Appartements, villas, voitures… → WhatsApp : {WA_NUMBER}",
}

MESSAGES_TRAITES = set()


def verifier_messages():
    """Vérifie et répond aux nouveaux messages Messenger."""
    url = f"{FB_API}/{PAGE_ID}/conversations"
    params = {
        "fields": "messages.limit(1){message,from,created_time,id}",
        "access_token": PAGE_ACCESS_TOKEN
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        conversations = data.get("data", [])

        for conv in conversations[:10]:
            messages = conv.get("messages", {}).get("data", [])
            if not messages:
                continue
            msg = messages[0]
            msg_id   = msg.get("id", "")
            texte    = msg.get("message", "").lower()
            expediteur = msg.get("from", {})

            # Ignorer nos propres messages et déjà traités
            if str(expediteur.get("id")) == str(PAGE_ID):
                continue
            if msg_id in MESSAGES_TRAITES:
                continue

            # Chercher une réponse
            for mot_cle, reponse in REPONSES.items():
                if mot_cle in texte:
                    ok = repondre_messenger(expediteur["id"], reponse)
                    if ok:
                        log.info(f"💬 Réponse envoyée à {expediteur.get('name','?')} (mot-clé: {mot_cle})")
                        MESSAGES_TRAITES.add(msg_id)
                    break

    except Exception as e:
        log.error(f"❌ Erreur Messenger : {e}")


# ═══════════════════════════════════════════════════════
#  RAPPORT HEBDOMADAIRE
# ═══════════════════════════════════════════════════════

def rapport_hebdomadaire():
    """Affiche les stats de la page."""
    log.info("📊 Rapport hebdomadaire NEXA Services")
    url = f"{FB_API}/{PAGE_ID}/insights"
    params = {
        "metric": "page_impressions,page_post_engagements,page_fans",
        "period": "week",
        "access_token": PAGE_ACCESS_TOKEN
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        for metric in data.get("data", []):
            valeurs = metric.get("values", [])
            val = valeurs[-1].get("value", 0) if valeurs else 0
            log.info(f"   📈 {metric.get('name')} : {val}")
    except Exception as e:
        log.error(f"❌ Erreur rapport : {e}")


# ═══════════════════════════════════════════════════════
#  POINT D'ENTRÉE PRINCIPAL
# ═══════════════════════════════════════════════════════

def demarrer():
    print("=" * 55)
    print("  NEXA Services — Automatisation Facebook (Railway)")
    print("=" * 55)

    if not verifier_config():
        log.error("Configure les variables dans Railway > Variables et redéploie.")
        return

    if not test_connexion():
        log.error("Vérifie ton PAGE_ID et PAGE_ACCESS_TOKEN dans Railway.")
        return

    charger_posts_publies()

    # Publication immédiate au démarrage
    publier_posts_du_jour()

    # Planification
    for h in HEURES:
        schedule.every().day.at(h).do(publier_posts_du_jour)
        log.info(f"⏰ Publication planifiée à {h}")

    schedule.every(15).minutes.do(verifier_messages)
    log.info("💬 Vérification Messenger toutes les 15 min")

    schedule.every().monday.at("08:00").do(rapport_hebdomadaire)
    log.info("📊 Rapport hebdomadaire chaque lundi à 08:00")

    log.info("─" * 50)
    log.info("✅ Automatisation active sur Railway 24h/24")
    log.info("─" * 50)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    demarrer()
