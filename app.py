from flask import Flask, render_template, request, jsonify
import requests
import logging

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

HEADERS = {
    "User-Agent": "WikiCategoryChecker/1.0 (User:Saroj; https://meta.wikimedia.org/wiki/User:Saroj)"
}

def wiki_domain(lang):
    return f"{lang}.wikipedia.org"

def fetch_json(url, params, timeout=15):
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
    return bool(fetch_json(url, params))

def page_exists(title, lang):
    url = f"https://{wiki_domain(lang)}/w/api.php"
    params = {"action": "query", "titles": title, "format": "json"}
    data = fetch_json(url, params)
    if not data:
        return False
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
    if not data:
        return []
    pages = data.get("query", {}).get("pages", {})
    cats = []
    for page in pages.values():
        cats.extend([c["title"].replace("Category:", "").strip() for c in page.get("categories", [])])
    return cats

def get_wikidata_qids_batch(categories, source_lang):
    titles = [f"Category:{c}" for c in categories]
    results = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "sites": f"{source_lang}wiki",
            "titles": "|".join(batch),
            "props": "sitelinks",
            "sitefilter": f"{source_lang}wiki",
            "format": "json"
        }
        data = fetch_json(url, params)
        if not data:
            continue
        for qid, entity in data.get("entities", {}).items():
            if qid == "-1":
                continue
            sitelinks = entity.get("sitelinks", {})
            src_title = sitelinks.get(f"{source_lang}wiki", {}).get("title", "").replace("Category:", "").strip()
            if src_title:
                results[src_title] = qid
    return results

def get_target_titles_batch(qid_map, target_lang):
    qids = list(set(qid_map.values()))
    qid_to_target = {}
    for i in range(0, len(qids), 50):
        batch = qids[i:i+50]
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "sitelinks",
            "sitefilter": f"{target_lang}wiki",
            "format": "json"
        }
        data = fetch_json(url, params)
        if not data:
            continue
        for qid, entity in data.get("entities", {}).items():
            title = entity.get("sitelinks", {}).get(f"{target_lang}wiki", {}).get("title")
            if title:
                qid_to_target[qid] = title.replace("Category:", "").strip()
    return qid_to_target

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
    if not source_cats:
        return {"categories": []}

    qid_map = get_wikidata_qids_batch(source_cats, source_lang)
    qid_to_target = get_target_titles_batch(qid_map, target_lang)

    return {"categories": list(qid_to_target.values())}

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