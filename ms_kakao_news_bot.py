import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
ROOT_DIR = Path(__file__).resolve().parent
SITE_DIR = ROOT_DIR / "site"
REPORT_PATH = SITE_DIR / "msft-report.html"
HISTORY_PATH = SITE_DIR / "score-history.json"
LOCAL_REPORT_URL = "http://localhost:8765/msft-report.html"
MESSAGE_PATH = SITE_DIR / "kakao-message.txt"

SENTIMENT_LABELS = {
    2: "Super Bull",
    1: "Bull",
    0: "Neutral",
    -1: "Bear",
    -2: "Super Bear",
}


def load_env(path=".env"):
    env_path = ROOT_DIR / path
    if not env_path.exists():
        return
    with env_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ms-kakao-news-bot/2.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def http_post_form(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_rss_datetime(value):
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def fetch_news(query, limit, lookback_hours):
    params = {
        "q": query,
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    }
    url = f"{GOOGLE_NEWS_RSS}?{urllib.parse.urlencode(params)}"
    root = ET.fromstring(http_get(url))
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    seen = set()
    articles = []

    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title"))
        link = clean_text(item.findtext("link"))
        summary = clean_text(item.findtext("description"))
        published = parse_rss_datetime(item.findtext("pubDate"))
        if published and published.astimezone(dt.timezone.utc) < cutoff:
            continue

        key = re.sub(r"\W+", "", title.lower())[:90]
        if not title or key in seen:
            continue
        seen.add(key)
        articles.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published": published.isoformat() if published else "",
            }
        )
        if len(articles) >= limit:
            break
    return articles


def normalize_score(value):
    try:
        score = int(value)
    except Exception:
        score = 0
    return max(-2, min(2, score))


def fallback_report(articles):
    rows = []
    for article in articles:
        text = f"{article['title']} {article.get('summary', '')}".lower()
        score = 0
        if any(word in text for word in ["growth", "surge", "record", "beat", "upgrade", "ai", "azure"]):
            score += 1
        if any(word in text for word in ["lawsuit", "probe", "decline", "outage", "risk", "layoff"]):
            score -= 1
        score = normalize_score(score)
        rows.append(
            {
                "title": article["title"],
                "summary": textwrap.shorten(article.get("summary") or article["title"], 105, placeholder="..."),
                "sentiment": SENTIMENT_LABELS[score],
                "score": score,
                "link": article["link"],
                "published": article.get("published", ""),
            }
        )

    total_score = sum(item["score"] for item in rows)
    return {
        "overview": f"최근 Microsoft 관련 뉴스 {len(rows)}건을 기준으로 산출한 일일 점수는 {total_score}점입니다.",
        "articles": rows,
        "total_score": total_score,
    }


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return json.loads(text)


def build_report_with_openai(articles):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_report(articles)

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    instructions = {
        "role": "system",
        "content": (
            "You are an equity-news analyst writing in Korean. Return strict JSON only. "
            "Do not include markdown. Be concise and avoid financial advice."
        ),
    }
    prompt = {
        "role": "user",
        "content": (
            "다음 Microsoft/MSFT 관련 뉴스 목록을 분석해 JSON으로 반환해줘.\n"
            "요구사항:\n"
            "- overview: 전체를 아우르는 한국어 한 문단 요약\n"
            "- articles: 입력 뉴스별 항목. 각 항목은 title, summary, sentiment, score, link, published 포함\n"
            "- summary는 한국어 한 줄 요약\n"
            "- sentiment는 반드시 Super Bull, Bull, Neutral, Bear, Super Bear 중 하나\n"
            "- score는 반드시 2, 1, 0, -1, -2 중 하나\n"
            "- MSFT 주가/사업 영향 관점으로 점수화하되 확정적 투자 조언처럼 쓰지 말 것\n"
            "- total_score는 articles score 합계\n\n"
            f"뉴스:\n{json.dumps(articles, ensure_ascii=False)}"
        ),
    }
    payload = {
        "model": model,
        "messages": [instructions, prompt],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))

    report = extract_json(data["choices"][0]["message"]["content"])
    normalized = []
    for index, item in enumerate(report.get("articles", [])):
        source = articles[index] if index < len(articles) else {}
        score = normalize_score(item.get("score", 0))
        normalized.append(
            {
                "title": clean_text(item.get("title") or source.get("title", "")),
                "summary": clean_text(item.get("summary") or source.get("summary", "")),
                "sentiment": SENTIMENT_LABELS[score],
                "score": score,
                "link": item.get("link") or source.get("link", ""),
                "published": item.get("published") or source.get("published", ""),
            }
        )
    total_score = sum(item["score"] for item in normalized)
    return {
        "overview": clean_text(report.get("overview", "")) or fallback_report(articles)["overview"],
        "articles": normalized,
        "total_score": total_score,
    }


def load_history():
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def update_history(total_score, article_count):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now().strftime("%Y-%m-%d")
    history = [item for item in load_history() if item.get("date") != today]
    history.append({"date": today, "score": total_score, "article_count": article_count})
    history = history[-120:]
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def score_class(score):
    if score == 2:
        return "super-bull"
    if score == 1:
        return "bull"
    if score == -1:
        return "bear"
    if score == -2:
        return "super-bear"
    return "neutral"


def render_report_html(report, articles, history):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    article_rows = []
    for index, item in enumerate(report["articles"], 1):
        score = normalize_score(item.get("score", 0))
        article_rows.append(
            f"""
            <tr>
              <td class="rank">{index}</td>
              <td>
                <a href="{html.escape(item.get('link', ''), quote=True)}" target="_blank" rel="noopener">
                  {html.escape(item.get('title', ''))}
                </a>
                <p>{html.escape(item.get('summary', ''))}</p>
              </td>
              <td><span class="badge {score_class(score)}">{html.escape(SENTIMENT_LABELS[score])}</span></td>
              <td class="score">{score:+d}</td>
            </tr>
            """
        )

    history_json = json.dumps(history, ensure_ascii=False)
    max_possible = max(1, len(report["articles"]) * 2)
    total_score = report["total_score"]
    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MSFT Daily Report</title>
  <style>
    :root {{
      --bg: #071426;
      --panel: #0d1f36;
      --panel-2: #102943;
      --line: #23415f;
      --text: #edf5ff;
      --muted: #9fb6ca;
      --cyan: #5bd6ff;
      --green: #4ade80;
      --lime: #a3e635;
      --gray: #94a3b8;
      --orange: #fb923c;
      --red: #fb7185;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
      letter-spacing: 0;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 28px 22px 48px; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 24px;
      padding-bottom: 22px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 34px; font-weight: 750; }}
    .sub {{ margin-top: 8px; color: var(--muted); }}
    .metric {{
      min-width: 210px;
      padding: 16px 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      text-align: right;
    }}
    .metric b {{ display: block; font-size: 34px; color: var(--cyan); }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 18px;
      margin-top: 22px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
    }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .overview {{ color: #dcecff; line-height: 1.7; margin: 0; }}
    .bars {{ height: 260px; display: flex; align-items: flex-end; gap: 8px; padding-top: 16px; }}
    .bar-wrap {{ flex: 1; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 8px; }}
    .bar {{ width: 100%; min-height: 3px; border-radius: 6px 6px 0 0; background: var(--cyan); }}
    .bar.negative {{ background: var(--red); }}
    .bar-label {{ writing-mode: vertical-rl; color: var(--muted); font-size: 11px; height: 58px; overflow: hidden; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 18px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 13px 12px; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-align: left; background: var(--panel-2); }}
    td.rank {{ width: 48px; color: var(--muted); }}
    td.score {{ width: 70px; text-align: right; font-weight: 800; font-size: 17px; }}
    a {{ color: var(--text); text-decoration: none; font-weight: 650; }}
    a:hover {{ color: var(--cyan); }}
    td p {{ margin: 6px 0 0; color: var(--muted); line-height: 1.5; }}
    .badge {{ display: inline-flex; min-width: 96px; justify-content: center; padding: 6px 8px; border-radius: 6px; font-size: 12px; font-weight: 800; color: #06111f; }}
    .super-bull {{ background: var(--green); }}
    .bull {{ background: var(--lime); }}
    .neutral {{ background: var(--gray); }}
    .bear {{ background: var(--orange); }}
    .super-bear {{ background: var(--red); }}
    footer {{ color: var(--muted); margin-top: 22px; font-size: 12px; }}
    @media (max-width: 820px) {{
      header, .grid {{ display: block; }}
      .metric {{ text-align: left; margin-top: 16px; }}
      section {{ margin-top: 16px; }}
      table {{ font-size: 13px; }}
      .badge {{ min-width: 80px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>MSFT Daily Report</h1>
        <div class="sub">최근 24시간 뉴스 {len(report["articles"])}개 분석 · 업데이트 {html.escape(now)}</div>
      </div>
      <div class="metric">
        <span>Daily Sentiment Score</span>
        <b>{total_score:+d}</b>
        <small>range {max_possible * -1:+d} to {max_possible:+d}</small>
      </div>
    </header>

    <div class="grid">
      <section>
        <h2>오늘의 한 문단</h2>
        <p class="overview">{html.escape(report["overview"])}</p>
      </section>
      <section>
        <h2>일일 점수 그래프</h2>
        <div class="bars" id="bars"></div>
      </section>
    </div>

    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>뉴스 한줄 요약</th>
          <th>판정</th>
          <th>점수</th>
        </tr>
      </thead>
      <tbody>
        {''.join(article_rows)}
      </tbody>
    </table>
    <footer>Scores: Super Bull +2, Bull +1, Neutral 0, Bear -1, Super Bear -2</footer>
  </div>
  <script>
    const history = {history_json};
    const bars = document.getElementById("bars");
    const maxAbs = Math.max(1, ...history.map((item) => Math.abs(item.score)));
    history.forEach((item) => {{
      const wrap = document.createElement("div");
      wrap.className = "bar-wrap";
      const bar = document.createElement("div");
      bar.className = "bar" + (item.score < 0 ? " negative" : "");
      bar.style.height = `${{Math.max(4, Math.abs(item.score) / maxAbs * 190)}}px`;
      bar.title = `${{item.date}}: ${{item.score > 0 ? "+" : ""}}${{item.score}}`;
      const label = document.createElement("div");
      label.className = "bar-label";
      label.textContent = item.date;
      wrap.appendChild(bar);
      wrap.appendChild(label);
      bars.appendChild(wrap);
    }});
  </script>
</body>
</html>"""
    REPORT_PATH.write_text(html_doc, encoding="utf-8")
    return REPORT_PATH


def build_kakao_message(report):
    report_url = os.getenv("REPORT_URL", LOCAL_REPORT_URL)
    lines = [
        "[MSFT Daily Report]",
        report["overview"],
        "",
        f"오늘 점수: {report['total_score']:+d}",
        f"홈페이지: {report_url}",
        "",
        "뉴스 한줄 요약:",
    ]
    for index, item in enumerate(report["articles"][:8], 1):
        score = normalize_score(item.get("score", 0))
        lines.append(f"{index}. [{SENTIMENT_LABELS[score]} {score:+d}] {item.get('summary', '')}")
    if len(report["articles"]) > 8:
        lines.append(f"...외 {len(report['articles']) - 8}개는 홈페이지에서 확인")
    return "\n".join(lines)


def refresh_kakao_access_token():
    rest_api_key = os.getenv("KAKAO_REST_API_KEY")
    refresh_token = os.getenv("KAKAO_REFRESH_TOKEN")
    if not rest_api_key or not refresh_token:
        raise RuntimeError("KAKAO_REST_API_KEY and KAKAO_REFRESH_TOKEN are required.")

    payload = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    client_secret = os.getenv("KAKAO_CLIENT_SECRET")
    if client_secret:
        payload["client_secret"] = client_secret

    data = http_post_form("https://kauth.kakao.com/oauth/token", payload)
    return data["access_token"]


def send_kakao_memo(text):
    access_token = refresh_kakao_access_token()
    template = {
        "object_type": "text",
        "text": textwrap.shorten(text, width=950, placeholder="\n..."),
        "link": {
            "web_url": os.getenv("REPORT_URL", LOCAL_REPORT_URL),
            "mobile_web_url": os.getenv("REPORT_URL", LOCAL_REPORT_URL),
        },
        "button_title": "리포트 열기",
    }
    return http_post_form(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": json.dumps(template, ensure_ascii=False)},
        headers={"Authorization": f"Bearer {access_token}"},
    )


def main():
    load_env()
    query = os.getenv("NEWS_QUERY", "Microsoft OR Azure OR Windows OR Copilot OR GitHub")
    limit = int(os.getenv("NEWS_LIMIT", "30"))
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "24"))
    dry_run = "--dry-run" in sys.argv
    generate_only = "--generate-only" in sys.argv
    send_only = "--send-only" in sys.argv
    # Additional flag to prevent duplicate sends within the same day.
    check_today = "--check-today" in sys.argv

    if send_only:
        if not MESSAGE_PATH.exists():
            raise RuntimeError(f"Missing message file: {MESSAGE_PATH}")
        result = send_kakao_memo(MESSAGE_PATH.read_text(encoding="utf-8"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    articles = fetch_news(query, limit, lookback_hours)
    report = build_report_with_openai(articles)
    history = update_history(report["total_score"], len(report["articles"]))
    report_path = render_report_html(report, articles, history)
    message = build_kakao_message(report)
    MESSAGE_PATH.write_text(message, encoding="utf-8")

    if dry_run or generate_only:
        print(message)
        print(f"\nReport: {report_path}")
        return

    # If the --check-today flag is provided, do not send a message again
    # if one has already been generated and sent today. This works by
    # checking the modification date of the saved message file.
    if check_today:
        if MESSAGE_PATH.exists():
            mod_time = dt.datetime.fromtimestamp(MESSAGE_PATH.stat().st_mtime)
            if mod_time.date() == dt.datetime.now().date():
                print("A message was already sent today; skipping send.")
                return

    result = send_kakao_memo(message)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
