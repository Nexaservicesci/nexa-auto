#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXA Services — Script d'automatisation Facebook v2 (Railway)
=============================================================
Génère ET publie automatiquement les posts via Claude API.

VARIABLES RAILWAY :
  PAGE_ID            → Page ID Facebook
  PAGE_ACCESS_TOKEN  → Page Access Token
  WA_NUMBER          → WhatsApp (+225 07 00 00 00 00)
  CLAUDE_API_KEY     → Clé API Claude (sk-ant-...)
"""

import json, os, time, logging, requests, schedule
from datetime import datetime, date

# ── CONFIG ──
PAGE_ID           = os.environ.get("PAGE_ID", "")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
WA_NUMBER         = os.environ.get("WA_NUMBER", "+225 07 00 00 00 00")
CLAUDE_API_KEY    = os.environ.get("CLAUDE_API_KEY", "")
EXPORT_FILE       = "NEXA_sauvegarde.json"
HEURES_PUB        = ["07:00", "12:00", "18:00", "20:00"]
FB_API            = "https://graph.facebook.com/v25.0"
CLAUDE_API        = "https://api.anthropic.com/v1/messages"
POSTS_PUBLIES_FILE = "posts_publies.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler()])
log = logging.getLogger("NEXA")

# ── VÉRIFICATION ──
def verifier_config():
    ok = True
    if not PAGE_ID:           log.error("❌ PAGE_ID manquant"); ok = False
    if not PAGE_ACCESS_TOKEN: log.error("❌ PAGE_ACCESS_TOKEN manquant"); ok = False
    if not CLAUDE_API_KEY:    log.warning("⚠️ CLAUDE_API_KEY manquante — génération auto désactivée")
    return ok

# ── FACEBOOK ──
def test_connexion():
    try:
        r = requests.get(f"{FB_API}/{PAGE_ID}", params={"fields":"name,fan_count","access_token":PAGE_ACCESS_TOKEN}, timeout=10)
        d = r.json()
        if "error" in d: log.error(f"❌ Token invalide : {d['error']['message']}"); return False
        log.info(f"✅ Connecté : {d.get('name')} — {d.get('fan_count',0)} abonnés")
        return True
    except Exception as e: log.error(f"❌ {e}"); return False

def publier_texte(texte):
    try:
        r = requests.post(f"{FB_API}/{PAGE_ID}/feed", data={"message":texte,"access_token":PAGE_ACCESS_TOKEN}, timeout=30)
        d = r.json()
        if "id" in d: log.info(f"✅ Publié — ID: {d['id']}"); return d["id"]
        log.error(f"❌ {d.get('error',{}).get('message','Erreur')}"); return None
    except Exception as e: log.error(f"❌ {e}"); return None

def publier_avec_photo(texte, src_b64):
    import base64, tempfile
    try:
        data_b64 = src_b64.split(",",1)[1] if src_b64.startswith("data:") else src_b64
        img = base64.b64decode(data_b64)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img); tmp_path = tmp.name
        with open(tmp_path,"rb") as f:
            r = requests.post(f"{FB_API}/{PAGE_ID}/photos",
                files={"source":("photo.jpg",f,"image/jpeg")},
                data={"message":texte,"access_token":PAGE_ACCESS_TOKEN}, timeout=60)
        os.unlink(tmp_path)
        d = r.json()
        if "id" in d: log.info(f"✅ Publié avec photo — ID: {d['id']}"); return d["id"]
        return publier_texte(texte)
    except Exception as e: log.error(f"❌ Photo: {e}"); return publier_texte(texte)

# ── CLAUDE API ──
def generer_post_ia(bien, type_post, page, contexte=""):
    if not CLAUDE_API_KEY:
        return generer_texte_fallback(bien, type_post, page)
    cats = {"appart":"appartement meublé","villa":"villa avec piscine","voiture":"véhicule de location","bureau":"bureau équipé","autre":"bien en location"}
    cat = cats.get(bien.get("cat","appart"), "bien en location")
    prompt = (
        f"Expert marketing immobilier Côte d'Ivoire. Rédige un post Facebook pour :\n"
        f"Page : {page.get('name','NEXA Services')} | WhatsApp : {page.get('wa', WA_NUMBER)}\n"
        f"Bien : {cat} \"{bien.get('name','')}\" à {bien.get('zone','')} | Prix : {bien.get('prix','')} FCFA\n"
        f"Équipements : {bien.get('equip','')}\n"
        f"Description : {bien.get('desc','')}\n"
        f"Disponibilité : {bien.get('dispo','disponible')}\n"
        f"Type de post : {type_post}{' | Contexte : ' + contexte if contexte else ''}\n"
        f"Hashtags : {page.get('ht','#NEXAServices #LocationAbidjan')}\n"
        f"Rédige un post complet : accroche, 2-3 paragraphes, emojis, hashtags, call-to-action WhatsApp. "
        f"Français, marché ivoirien, 150-200 mots."
    )
    try:
        r = requests.post(CLAUDE_API,
            headers={"Content-Type":"application/json","x-api-key":CLAUDE_API_KEY,"anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":600,"messages":[{"role":"user","content":prompt}]},
            timeout=30)
        d = r.json()
        if "error" in d: raise Exception(d["error"].get("message","Erreur Claude"))
        texte = d["content"][0]["text"]
        log.info(f"✅ Post généré par IA pour {bien.get('name','')}")
        return texte
    except Exception as e:
        log.warning(f"⚠️ Claude API: {e} — fallback texte simple")
        return generer_texte_fallback(bien, type_post, page)

def generer_texte_fallback(bien, type_post, page):
    wa = page.get("wa", WA_NUMBER)
    ht = page.get("ht", "#NEXAServices #LocationAbidjan")
    nom = bien.get("name",""); zone = bien.get("zone",""); prix = bien.get("prix",""); equip = bien.get("equip","")
    emojis = {"appart":"🏠","villa":"🏡","voiture":"🚗","bureau":"🏢","autre":"📦"}
    e = emojis.get(bien.get("cat","appart"),"🏠")
    if type_post == "Promotion":
        return f"🔥 OFFRE SPÉCIALE — {nom}\n\n📍 {zone}\n💰 {prix} FCFA\n✅ {equip}\n\n⚡ Réservez vite !\n📲 WhatsApp : {wa}\n\n{ht}"
    elif type_post == "Présentation":
        return f"✨ Découvrez {nom}\n\n📍 {zone}\n💰 {prix} FCFA\n🛎️ {equip}\n\n📲 {wa}\n\n{ht}"
    else:
        return f"{e} {nom} est disponible !\n\n📍 {zone}\n💰 {prix} FCFA\n✅ {equip}\n\n📲 {wa}\n\n{ht}"

# ── GÉNÉRATION AUTOMATIQUE HEBDOMADAIRE ──
TYPES_ROTATION = ["Disponibilité", "Présentation", "Promotion", "Disponibilité", "Weekend spécial", "Présentation", "Promotion"]

def generer_et_planifier_semaine():
    log.info("🤖 Génération automatique des posts de la semaine...")
    data = charger_export()
    if not data: return
    biens = data.get("biens", [])
    page  = data.get("page", {})
    if not biens: log.warning("⚠️ Aucun bien dans le fichier export"); return

    aujourd_hui = date.today()
    posts_generes = []
    for i, bien in enumerate(biens):
        # Un post par bien, réparti sur les 7 prochains jours
        jour = aujourd_hui.fromordinal(aujourd_hui.toordinal() + (i % 7))
        type_post = TYPES_ROTATION[i % len(TYPES_ROTATION)]
        texte = generer_post_ia(bien, type_post, page)
        photo = trouver_meilleure_photo(bien)
        posts_generes.append({
            "date": jour.isoformat(),
            "time": "18:00",
            "type": type_post,
            "text": texte,
            "bienId": bien.get("id"),
            "bienName": bien.get("name"),
            "bienCat": bien.get("cat"),
            "photo": photo
        })
        time.sleep(0.5)  # Éviter le rate limiting

    # Sauvegarder les posts générés
    with open("posts_semaine.json","w",encoding="utf-8") as f:
        json.dump(posts_generes, f, ensure_ascii=False, indent=2)
    log.info(f"✅ {len(posts_generes)} posts générés et sauvegardés pour la semaine")

def trouver_meilleure_photo(bien):
    medias = bien.get("media", [])
    for m in medias:
        if m.get("isOpt") and m.get("type") == "photo":
            src = m.get("optimizedSrc") or m.get("src","")
            if src.startswith("data:image"): return src
    for m in medias:
        if m.get("type") == "photo":
            src = m.get("src","")
            if src.startswith("data:image"): return src
    return None

# ── PUBLICATION DU JOUR ──
POSTS_PUBLIES = set()

def charger_posts_publies():
    global POSTS_PUBLIES
    if os.path.exists(POSTS_PUBLIES_FILE):
        try:
            with open(POSTS_PUBLIES_FILE,"r",encoding="utf-8") as f:
                POSTS_PUBLIES = set(json.load(f))
        except: pass
    log.info(f"📋 {len(POSTS_PUBLIES)} posts déjà publiés")

def sauvegarder_posts_publies():
    with open(POSTS_PUBLIES_FILE,"w",encoding="utf-8") as f:
        json.dump(list(POSTS_PUBLIES), f)

def charger_export():
    # Essayer d'abord le fichier de la semaine généré automatiquement
    for fname in ["posts_semaine.json", EXPORT_FILE]:
        if os.path.exists(fname):
            try:
                with open(fname,"r",encoding="utf-8") as f:
                    data = json.load(f)
                # posts_semaine.json est une liste directe
                if isinstance(data, list):
                    return {"scheduled": data, "biens": [], "page": {}}
                log.info(f"📂 {fname} chargé : {len(data.get('biens',[]))} biens, {len(data.get('scheduled',[]))} posts")
                return data
            except Exception as e:
                log.error(f"❌ Erreur lecture {fname}: {e}")
    log.warning("⚠️ Aucun fichier de posts trouvé")
    return None

def publier_posts_du_jour():
    log.info("─"*50)
    log.info("🚀 Vérification des posts à publier...")
    data = charger_export()
    if not data: return
    aujourd_hui = date.today().isoformat()
    posts_jour = [p for p in data.get("scheduled",[]) if p.get("date") == aujourd_hui]
    log.info(f"📅 {len(posts_jour)} post(s) pour aujourd'hui ({aujourd_hui})")
    if not posts_jour: log.info("✅ Rien à publier aujourd'hui"); return

    publies = 0
    for post in posts_jour:
        pid = f"{post.get('date')}_{post.get('bienId')}_{post.get('type')}"
        if pid in POSTS_PUBLIES: log.info(f"⏩ Déjà publié : {post.get('bienName')}"); continue
        texte = post.get("text","")
        if not texte: continue
        photo = post.get("photo")
        log.info(f"📤 {post.get('bienName')} / {post.get('type')} {'📷' if photo else '📝'}")
        result = publier_avec_photo(texte, photo) if photo else publier_texte(texte)
        if result:
            POSTS_PUBLIES.add(pid); sauvegarder_posts_publies(); publies += 1
            if len(posts_jour) > 1: time.sleep(30*60)
    log.info(f"✅ {publies}/{len(posts_jour)} post(s) publiés")

# ── MESSENGER ──
REPONSES = {
    "appartement": f"Bonjour 😊 Nous avons plusieurs appartements disponibles à Abidjan. → WhatsApp : {WA_NUMBER}",
    "appart":      f"Bonjour 😊 Appartements disponibles ! → WhatsApp : {WA_NUMBER}",
    "villa":       f"Bonjour 🏡 Villas avec piscine disponibles ! → WhatsApp : {WA_NUMBER}",
    "voiture":     f"Bonjour 🚗 Véhicules disponibles ! → WhatsApp : {WA_NUMBER}",
    "prix":        "Appartements dès 35 000 FCFA/nuit · Villas dès 80 000 FCFA/nuit · Voitures dès 25 000 FCFA/jour.",
    "tarif":       "Appartements dès 35 000 FCFA/nuit · Villas dès 80 000 FCFA/nuit · Voitures dès 25 000 FCFA/jour.",
    "disponible":  f"Bonjour ! Précisez le type de bien et vos dates → WhatsApp : {WA_NUMBER}",
    "reserv":      f"Pour réserver → WhatsApp : {WA_NUMBER}",
    "bonjour":     f"Bonjour 😊 Comment puis-je vous aider ? → WhatsApp : {WA_NUMBER}",
    "merci":       "Merci pour votre confiance ! 🙏 À bientôt !",
}
MESSAGES_TRAITES = set()

def verifier_messages():
    try:
        r = requests.get(f"{FB_API}/{PAGE_ID}/conversations",
            params={"fields":"messages.limit(1){message,from,id}","access_token":PAGE_ACCESS_TOKEN}, timeout=10)
        for conv in r.json().get("data",[])[:10]:
            msgs = conv.get("messages",{}).get("data",[])
            if not msgs: continue
            msg = msgs[0]; mid = msg.get("id",""); texte = msg.get("message","").lower()
            exp = msg.get("from",{})
            if str(exp.get("id")) == str(PAGE_ID) or mid in MESSAGES_TRAITES: continue
            for mot, rep in REPONSES.items():
                if mot in texte:
                    r2 = requests.post(f"{FB_API}/me/messages",
                        json={"recipient":{"id":exp["id"]},"message":{"text":rep},"access_token":PAGE_ACCESS_TOKEN}, timeout=10)
                    if "message_id" in r2.json():
                        log.info(f"💬 Réponse à {exp.get('name','?')} (mot-clé: {mot})")
                        MESSAGES_TRAITES.add(mid)
                    break
    except Exception as e: log.error(f"❌ Messenger: {e}")

def rapport_hebdomadaire():
    log.info("📊 Rapport hebdomadaire NEXA Services")
    try:
        r = requests.get(f"{FB_API}/{PAGE_ID}/insights",
            params={"metric":"page_impressions,page_post_engagements,page_fans","period":"week","access_token":PAGE_ACCESS_TOKEN}, timeout=10)
        for m in r.json().get("data",[]):
            vals = m.get("values",[]); val = vals[-1].get("value",0) if vals else 0
            log.info(f"   📈 {m.get('name')} : {val}")
    except Exception as e: log.error(f"❌ Rapport: {e}")

# ── MAIN ──
def demarrer():
    print("="*55)
    print("  NEXA Services — Automatisation Facebook v2")
    print("  Génération IA + Publication automatique")
    print("="*55)
    if not verifier_config(): return
    if not test_connexion(): return
    charger_posts_publies()

    # Génération immédiate si CLAUDE_API_KEY présente
    if CLAUDE_API_KEY:
        log.info("🤖 CLAUDE_API_KEY détectée — génération automatique activée")
        generer_et_planifier_semaine()
    else:
        log.info("ℹ️ Sans CLAUDE_API_KEY — utilise le fichier NEXA_sauvegarde.json")

    publier_posts_du_jour()

    # Planification publications
    for h in HEURES_PUB:
        schedule.every().day.at(h).do(publier_posts_du_jour)
        log.info(f"⏰ Publication planifiée à {h}")

    # Génération auto chaque lundi à 6h
    if CLAUDE_API_KEY:
        schedule.every().monday.at("06:00").do(generer_et_planifier_semaine)
        log.info("🤖 Génération automatique chaque lundi à 06:00")

    schedule.every(15).minutes.do(verifier_messages)
    log.info("💬 Vérification Messenger toutes les 15 min")
    schedule.every().monday.at("08:00").do(rapport_hebdomadaire)
    log.info("📊 Rapport hebdomadaire chaque lundi à 08:00")

    log.info("─"*50)
    log.info("✅ Automatisation active sur Railway 24h/24")
    log.info("─"*50)

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    demarrer()
