from flask import Flask, render_template, request, jsonify
import requests
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

HEADERS = {
    "User-Agent": "WikiCategoryChecker/1.0 (User:Saroj; https://meta.wikimedia.org/wiki/User:Saroj)"
}

qid_cache = {}
target_cache = {}

def wiki_domain(lang):
    return f"{lang}.wikipedia.org"

def fetch_json(url, params, timeout=5):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logging.warning(f"Request failed for {url} with params {params}: {e}")
        return None

def wiki_exists(lang):
    url = f"https://{wiki_domain(lang)}/w/api.php"
    params = {"action": "query", "meta": "siteinfo", "format": "json"}
    data = fetch_json(url, params)
    return bool(data)

def page_exists(title, lang):
    url = f"https://{wiki_domain(lang)}/w/api.php"
    params = {"action": "query", "titles": title, "format": "json"}
    data = fetch_json(url, params)
    if not data: return False
    pages = data.get("query", {}).get("pages", {})
    return "-1" not in pages

def get_categories(title, lang):
    url = f"https://{wiki_domain(lang)}/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "categories",
        "cllimit": "max",
        "clshow": "!hidden",
        "format": "json"
    }
    data = fetch_json(url, params)
    if not data: return []

    pages = data.get("query", {}).get("pages", {})
    cats = []
    for page in pages.values():
        cats.extend([c["title"].replace("Category:", "").strip() for c in page.get("categories", [])])
    return cats

def get_wikidata_qid(category, source_lang):
    if category in qid_cache: return qid_cache[category]
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbgetentities",
        "sites": f"{source_lang}wiki",
        "titles": f"Category:{category}",
        "format": "json"
    }
    data = fetch_json(url, params)
    if not data: return None
    entities = data.get("entities", {})
    for qid in entities:
        if qid != "-1":
            qid_cache[category] = qid
            return qid
    return None

def get_target_category_title(qid, target_lang):
    if not qid: return None
    cache_key = f"{qid}-{target_lang}"
    if cache_key in target_cache: return target_cache[cache_key]
    url = "https://www.wikidata.org/w/api.php"
    params = {"action": "wbgetentities", "ids": qid, "props": "sitelinks", "format": "json"}
    data = fetch_json(url, params)
    if not data: return None
    entity = data.get("entities", {}).get(qid, {})
    sitelinks = entity.get("sitelinks", {})
    title = sitelinks.get(f"{target_lang}wiki", {}).get("title")
    if title: target_cache[cache_key] = title
    return title

def check_category(cat, source_lang, target_lang):
    qid = get_wikidata_qid(cat, source_lang)
    return get_target_category_title(qid, target_lang)

def category_check_logic(source_lang, target_lang, page_title):
    source_lang = source_lang.lower().strip()
    target_lang = target_lang.lower().strip()
    page_title = page_title.strip().replace("_", " ")

    if not wiki_exists(source_lang):
        return {"error": f"Source wiki '{source_lang}' does not exist."}
    if not wiki_exists(target_lang):
        return {"error": f"Target wiki '{target_lang}' does not exist."}
    if not page_exists(page_title, source_lang):
        return {"error": f"Page '{page_title}' does not exist in {source_lang}wiki."}

    source_cats = get_categories(page_title, source_lang)
    categories_exist = []
    for c in source_cats:
        target_title = check_category(c, source_lang, target_lang)
        if target_title:
            categories_exist.append(target_title)
    return {"categories": categories_exist}

@app.route("/")
def home():
    return render_template("check.html")

@app.route("/api/categorycheck", methods=["POST"])
def category_check_api():
    data = request.get_json()
    source_lang = data.get("source_lang", "").strip()
    target_lang = data.get("target_lang", "").strip()
    page_title = data.get("page_title", "").strip()
    if not source_lang or not target_lang or not page_title:
        return jsonify({"error": "Please fill in all fields."})

    result = category_check_logic(source_lang, target_lang, page_title)
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
