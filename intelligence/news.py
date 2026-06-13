import feedparser
import requests
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Free RSS news feeds - no API key needed
NEWS_FEEDS = {
    "ForexLive":      "https://www.forexlive.com/feed/news",
    "Reuters FX":     "https://feeds.reuters.com/reuters/businessNews",
    "MarketWatch":    "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "Investing.com":  "https://www.investing.com/rss/news.rss",
}

# Keywords that move forex and gold markets
HIGH_IMPACT_KEYWORDS = [
    "federal reserve", "fed", "fomc", "interest rate", "rate hike", "rate cut",
    "jerome powell", "powell", "inflation", "cpi", "jobs report", "nfp",
    "non-farm payroll", "gdp", "recession", "unemployment", "central bank",
    "ecb", "european central bank", "bank of england", "boe",
    "gold", "xau", "dollar", "usd", "eur", "gbp",
    "war", "conflict", "sanctions", "geopolitical",
    "tariff", "trade war", "china", "russia"
]

BULLISH_GOLD_KEYWORDS = [
    "war", "conflict", "uncertainty", "crisis", "inflation surge",
    "rate cut", "dollar weakness", "recession fears", "safe haven"
]

BEARISH_GOLD_KEYWORDS = [
    "rate hike", "strong dollar", "risk on", "economic growth",
    "dollar strength", "fed hawkish"
]


# ─────────────────────────────────────────────
#  FETCH NEWS FROM RSS FEEDS
# ─────────────────────────────────────────────
def fetch_news(max_articles=20):
    """
    Fetch latest financial news from free RSS feeds.
    Returns list of articles with title, summary, source, time.
    """
    all_articles = []

    for source, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")[:200]
                pub     = entry.get("published", "")

                all_articles.append({
                    "source":  source,
                    "title":   title,
                    "summary": summary,
                    "time":    pub,
                    "url":     entry.get("link", "")
                })
        except Exception as e:
            print(f"   Could not fetch {source}: {e}")
            continue

    return all_articles[:max_articles]


# ─────────────────────────────────────────────
#  FILTER HIGH IMPACT NEWS
# ─────────────────────────────────────────────
def filter_high_impact(articles):
    """
    Filter articles that are likely to move the market.
    Returns only articles containing high-impact keywords.
    """
    high_impact = []

    for article in articles:
        text = (article["title"] + " " + article["summary"]).lower()
        matches = [kw for kw in HIGH_IMPACT_KEYWORDS if kw in text]

        if matches:
            article["keywords"] = matches
            article["impact_score"] = len(matches)
            high_impact.append(article)

    # Sort by impact score
    high_impact.sort(key=lambda x: x["impact_score"], reverse=True)
    return high_impact


# ─────────────────────────────────────────────
#  GET NEWS SUMMARY FOR AI
# ─────────────────────────────────────────────
def get_news_summary(instrument="EUR_USD"):
    """
    Get a clean news summary the AI brain can read.
    Returns a formatted string of top market-moving headlines.
    """
    print("\nFetching latest market news...")
    articles = fetch_news()
    high_impact = filter_high_impact(articles)

    if not high_impact:
        return "No significant market-moving news found in last fetch."

    summary_lines = [f"Top {min(5, len(high_impact))} market-moving headlines:"]

    for i, article in enumerate(high_impact[:5]):
        summary_lines.append(
            f"{i+1}. [{article['source']}] {article['title']}"
        )

    summary = "\n".join(summary_lines)

    print(f"\nNews Summary:")
    print("=" * 52)
    print(summary)
    print("=" * 52)

    return summary


# ─────────────────────────────────────────────
#  TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Trading AI - News Feed Test")
    print("=" * 52)

    articles = fetch_news()
    print(f"\nFetched {len(articles)} total articles")

    high_impact = filter_high_impact(articles)
    print(f"High impact articles: {len(high_impact)}")

    print("\nTop Headlines:")
    for i, a in enumerate(high_impact[:5]):
        print(f"\n{i+1}. {a['title']}")
        print(f"   Source   : {a['source']}")
        print(f"   Keywords : {', '.join(a['keywords'][:3])}")
        print(f"   Impact   : {a['impact_score']}")

    summary = get_news_summary()
    print("\nNews test complete!")
