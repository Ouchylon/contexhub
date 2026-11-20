"""Classement commun des visites par canal (Shopify, GA4). Aucune donnée personnelle."""
import re
from urllib.parse import urlparse

IA = re.compile(r"chatgpt|openai|perplexity|gemini|bard|copilot|claude\.ai|you\.com|mistral|deepseek", re.I)
RECHERCHE = re.compile(r"(^|\.)(google|bing|duckduckgo|yahoo|ecosia|qwant|brave)\.", re.I)
SOCIAL = re.compile(r"facebook|instagram|fb\.|lnkd|linkedin|t\.co|twitter|x\.com|youtube|tiktok|reddit", re.I)

ORDRE = ["Meta (pub)", "Google Ads", "Courriel", "LinkedIn (pub)", "Recherche Google (SEO)",
         "IA (ChatGPT, etc.)", "Réseaux sociaux (organique)", "Sites référents", "Direct / inconnu"]


def canal(utm=None, referrer=None, source=None):
    u = {k: (v or "").lower() for k, v in (utm or {}).items()}
    src, med = u.get("source", ""), u.get("medium", "")
    host = (urlparse(referrer).netloc if referrer else "").lower()
    s = (source or "").lower()
    if src or med:
        if re.search(r"email|e-mail|newsletter|courriel", med + " " + src) or src in ("dialog", "di", "dialoginsight", "shopify_email"):
            return "Courriel"
        paye = re.search(r"cpc|ppc|paid|ads|display|boost", med)
        if re.search(r"facebook|instagram|meta|fb|ig", src):
            return "Meta (pub)" if paye else "Réseaux sociaux (organique)"
        if "linkedin" in src:
            return "LinkedIn (pub)" if paye else "Réseaux sociaux (organique)"
        if re.search(r"google|adwords", src) and paye:
            return "Google Ads"
        if IA.search(src):
            return "IA (ChatGPT, etc.)"
        if re.search(r"organic|seo", med):
            return "Recherche Google (SEO)"
        return "Sites référents"
    if host:
        if IA.search(host):
            return "IA (ChatGPT, etc.)"
        if RECHERCHE.search(host):
            return "Recherche Google (SEO)"
        if SOCIAL.search(host):
            return "Réseaux sociaux (organique)"
        if "contech.qc.ca" in host or "myshopify" in host:
            return "Direct / inconnu"
        return "Sites référents"
    if IA.search(s):
        return "IA (ChatGPT, etc.)"
    if re.search(r"google|bing", s):
        return "Recherche Google (SEO)"
    if SOCIAL.search(s):
        return "Réseaux sociaux (organique)"
    if re.search(r"email|mail", s):
        return "Courriel"
    return "Direct / inconnu"


def canal_ga4(groupe, source=""):
    """Traduit le « Default channel group » de GA4 vers nos canaux."""
    g, s = (groupe or "").lower(), (source or "").lower()
    if IA.search(s):
        return "IA (ChatGPT, etc.)"
    if g == "paid social":
        return "LinkedIn (pub)" if "linkedin" in s else "Meta (pub)"
    if g in ("paid search", "cross-network", "paid other", "display", "paid video", "paid shopping"):
        return "Google Ads" if "google" in s or g != "paid other" else "Sites référents"
    if g == "email":
        return "Courriel"
    if g in ("organic search", "organic shopping"):
        return "Recherche Google (SEO)"
    if g in ("organic social", "organic video"):
        return "Réseaux sociaux (organique)"
    if g == "referral":
        return "Sites référents"
    return "Direct / inconnu"
