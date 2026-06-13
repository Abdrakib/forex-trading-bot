import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from textblob import TextBlob

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─────────────────────────────────────────────
#  ANALYZE SINGLE HEADLINE
# ─────────────────────────────────────────────
def analyze_headline(headline):
    """
    Analyze sentiment of a single news headline.
    Returns polarity score from -1.0 (bearish) to +1.0 (bullish)
    """
    blob      = TextBlob(headline)
    polarity  = blob.sentiment.polarity
    subjectivity = blob.sentiment.subjectivity

    if polarity > 0.1:
        sentiment = "BULLISH"
    elif polarity < -0.1:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    return {
        "headline":     headline,
        "polarity":     round(polarity, 3),
        "subjectivity": round(subjectivity, 3),
        "sentiment":    sentiment
    }


# ─────────────────────────────────────────────
#  ANALYZE MULTIPLE HEADLINES
# ─────────────────────────────────────────────
def analyze_headlines(headlines):
    """
    Analyze a list of headlines and return aggregate sentiment.
    """
    if not headlines:
        return None

    results   = [analyze_headline(h) for h in headlines]
    polarities = [r["polarity"] for r in results]

    avg_polarity = sum(polarities) / len(polarities)

    if avg_polarity > 0.1:
        overall = "BULLISH"
    elif avg_polarity < -0.1:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"

    bullish_count = sum(1 for r in results if r["sentiment"] == "BULLISH")
    bearish_count = sum(1 for r in results if r["sentiment"] == "BEARISH")
    neutral_count = sum(1 for r in results if r["sentiment"] == "NEUTRAL")

    return {
        "overall_sentiment": overall,
        "avg_polarity":      round(avg_polarity, 3),
        "bullish_count":     bullish_count,
        "bearish_count":     bearish_count,
        "neutral_count":     neutral_count,
        "total_analyzed":    len(results),
        "individual":        results
    }


# ─────────────────────────────────────────────
#  GET SENTIMENT SCORE FOR AI
# ─────────────────────────────────────────────
def get_sentiment_context(news_articles):
    """
    Takes news articles and returns a sentiment summary
    the AI brain can use in its decision making.
    """
    if not news_articles:
        return "No news available for sentiment analysis.", 0

    headlines = [a["title"] for a in news_articles[:10]]
    result    = analyze_headlines(headlines)

    if not result:
        return "Sentiment analysis unavailable.", 0

    context = (
        f"Market Sentiment Analysis ({result['total_analyzed']} headlines):\n"
        f"  Overall     : {result['overall_sentiment']}\n"
        f"  Avg Score   : {result['avg_polarity']} (-1=bearish, +1=bullish)\n"
        f"  Bullish     : {result['bullish_count']} headlines\n"
        f"  Bearish     : {result['bearish_count']} headlines\n"
        f"  Neutral     : {result['neutral_count']} headlines"
    )

    print("\nSentiment Analysis:")
    print("=" * 52)
    print(context)
    print("=" * 52)

    return context, result["avg_polarity"]


# ─────────────────────────────────────────────
#  TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("Trading AI - Sentiment Analysis Test")
    print("=" * 52)

    test_headlines = [
        "Federal Reserve signals more rate hikes ahead as inflation remains high",
        "Gold surges as geopolitical tensions escalate in Middle East",
        "US economy shows strong job growth, dollar strengthens",
        "ECB considers pausing rate hikes amid economic slowdown",
        "Powell warns of further tightening if inflation persists",
        "Gold falls as risk appetite improves on trade deal optimism",
        "US CPI comes in higher than expected, markets tumble",
    ]

    print("\nAnalyzing individual headlines:")
    for headline in test_headlines:
        result = analyze_headline(headline)
        bar    = "+" * int(abs(result["polarity"]) * 10)
        direction = "+" if result["polarity"] >= 0 else "-"
        print(f"\n  [{result['sentiment']:<8}] {headline[:60]}")
        print(f"  Score: {direction}{abs(result['polarity']):.3f} |{bar}|")

    print("\n\nAggregate sentiment:")
    mock_articles = [{"title": h} for h in test_headlines]
    context, score = get_sentiment_context(mock_articles)

    print("\nSentiment test complete!")
