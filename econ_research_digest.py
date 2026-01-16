#!/usr/bin/env python3
"""
Economics Research Digest Generator
Aggregates new working papers from top economics sources, filtered for Groundwork priorities.

Usage:
    python econ_research_digest.py                    # Last 7 days
    python econ_research_digest.py --days 14          # Last 14 days
    python econ_research_digest.py --output digest.md # Custom output file
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import re
import argparse
import time
import os

# =============================================================================
# CONFIGURATION - Edit these to customize
# =============================================================================

# Keywords relevant to Groundwork's priorities (case-insensitive)
PRIORITY_KEYWORDS = [
    # Corporate power & pricing
    "price", "pricing", "markup", "profit", "corporate", "concentration", 
    "monopoly", "antitrust", "market power", "oligopoly", "merger",
    "gouging", "inflation",
    
    # Housing
    "housing", "rent", "mortgage", "landlord", "eviction", "tenant",
    "homeowner", "affordability", "real estate", "financialization",
    
    # Labor & wages
    "wage", "labor", "worker", "employment", "unemployment", "union",
    "minimum wage", "gig economy", "collective bargaining", "strike",
    
    # Inequality & distribution
    "inequality", "wealth", "income distribution", "poverty", "mobility",
    "racial", "gender gap", "disparity", "progressive",
    
    # Consumer & household
    "consumer", "household", "debt", "credit", "family", "childcare",
    "healthcare cost", "food price", "grocery",
    
    # Policy
    "tax", "fiscal", "subsidy", "regulation", "enforcement", "antitrust",
    "competition policy", "industrial policy",
]

# RSS Feeds and sources
SOURCES = {
    "VoxEU/CEPR": {
        "url": "https://cepr.org/rss/voxeu/columns.xml",
        "type": "rss"
    },
    "Equitable Growth": {
        "url": "https://equitablegrowth.org/feed/",
        "type": "rss"
    },
    "EPI": {
        "url": "https://www.epi.org/feed/",
        "type": "rss"
    },
    "Fed Board Working Papers": {
        "url": "https://www.federalreserve.gov/feeds/feds.xml",
        "type": "rss"
    },
    "NY Fed Research": {
        "url": "https://libertystreeteconomics.newyorkfed.org/feed/",
        "type": "rss"
    },
    "SF Fed Economic Letters": {
        "url": "https://www.frbsf.org/research-and-insights/publications/economic-letter/rss-feed/",
        "type": "rss"
    },
    "Brookings Economics": {
        "url": "https://www.brookings.edu/feed/?topic=economy",
        "type": "rss"
    },
    "SSRN Economics": {
        "url": "https://papers.ssrn.com/sol3/Jeljour_results.cfm?form_name=journalBrowse&journal_id=918&Network=no&lim=false&npage=1",
        "type": "scrape_ssrn"
    },
}

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Paper:
    title: str
    authors: str
    source: str
    url: str
    abstract: str
    date: Optional[datetime]
    relevance_score: int = 0
    matched_keywords: list = None
    key_finding: str = ""
    
    def __post_init__(self):
        if self.matched_keywords is None:
            self.matched_keywords = []

# =============================================================================
# CONTENT FETCHING & SUMMARIZATION
# =============================================================================

def fetch_full_content(url: str) -> str:
    """Fetch and extract main text content from a paper's page."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; research aggregator)'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script, style, nav elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        
        # Try common article containers
        content = None
        for selector in ['article', '.post-content', '.entry-content', '.article-body', 
                         '.content', 'main', '.paper-abstract', '.abstract']:
            content = soup.select_one(selector)
            if content:
                break
        
        if not content:
            content = soup.body
        
        text = content.get_text(separator=' ', strip=True) if content else ""
        # Limit to ~3000 chars to keep API costs down
        return text[:3000]
    except Exception as e:
        print(f"    Warning: Could not fetch {url}: {e}")
        return ""

def summarize_with_claude(title: str, abstract: str, full_content: str) -> str:
    """Use Claude API to generate a one-sentence key finding."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return ""
    
    try:
        prompt = f"""Based on this economics paper, provide ONE sentence (max 30 words) stating the key finding or takeaway. Be specific with numbers/percentages if available. Focus on the "so what" for policymakers.

Title: {title}

Abstract: {abstract}

Content excerpt: {full_content[:2000]}

Key finding (one sentence):"""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['content'][0]['text'].strip()
        else:
            print(f"    API error: {response.status_code}")
            return ""
    except Exception as e:
        print(f"    Summarization error: {e}")
        return ""

def enrich_paper_with_summary(paper: Paper) -> Paper:
    """Fetch content and generate summary for a paper."""
    print(f"    Summarizing: {paper.title[:50]}...")
    full_content = fetch_full_content(paper.url)
    paper.key_finding = summarize_with_claude(paper.title, paper.abstract, full_content)
    time.sleep(0.5)  # Rate limiting
    return paper

# =============================================================================
# KEYWORD MATCHING
# =============================================================================

def calculate_relevance(paper: Paper) -> Paper:
    """Score paper relevance based on keyword matches in title and abstract."""
    text = f"{paper.title} {paper.abstract}".lower()
    matches = []
    
    for keyword in PRIORITY_KEYWORDS:
        if keyword.lower() in text:
            matches.append(keyword)
            # Title matches worth more
            if keyword.lower() in paper.title.lower():
                paper.relevance_score += 3
            else:
                paper.relevance_score += 1
    
    paper.matched_keywords = list(set(matches))
    return paper

# =============================================================================
# RSS PARSING
# =============================================================================

def parse_rss_feed(source_name: str, url: str, cutoff_date: datetime) -> list[Paper]:
    """Parse a standard RSS feed."""
    papers = []
    
    try:
        feed = feedparser.parse(url)
        
        for entry in feed.entries:
            # Parse date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6])
            
            # Skip if older than cutoff
            if pub_date and pub_date < cutoff_date:
                continue
            
            # Extract abstract/summary
            abstract = ""
            if hasattr(entry, 'summary'):
                abstract = BeautifulSoup(entry.summary, 'html.parser').get_text()[:500]
            elif hasattr(entry, 'description'):
                abstract = BeautifulSoup(entry.description, 'html.parser').get_text()[:500]
            
            # Extract authors
            authors = ""
            if hasattr(entry, 'author'):
                authors = entry.author
            elif hasattr(entry, 'authors'):
                authors = ", ".join([a.get('name', '') for a in entry.authors])
            
            paper = Paper(
                title=entry.title,
                authors=authors,
                source=source_name,
                url=entry.link,
                abstract=abstract.strip(),
                date=pub_date
            )
            papers.append(calculate_relevance(paper))
            
    except Exception as e:
        print(f"  Warning: Error parsing {source_name}: {e}")
    
    return papers

def scrape_ssrn(source_name: str, url: str, cutoff_date: datetime) -> list[Paper]:
    """Scrape SSRN economics papers (they don't have a clean RSS)."""
    papers = []
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; research aggregator)'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # SSRN structure varies, this is a best-effort parse
        for item in soup.select('.paper-result, .result-item')[:20]:
            title_elem = item.select_one('.title a, h3 a')
            if not title_elem:
                continue
                
            title = title_elem.get_text(strip=True)
            link = title_elem.get('href', '')
            if link and not link.startswith('http'):
                link = f"https://papers.ssrn.com{link}"
            
            authors_elem = item.select_one('.authors, .author')
            authors = authors_elem.get_text(strip=True) if authors_elem else ""
            
            abstract_elem = item.select_one('.abstract, .description')
            abstract = abstract_elem.get_text(strip=True)[:500] if abstract_elem else ""
            
            paper = Paper(
                title=title,
                authors=authors,
                source=source_name,
                url=link,
                abstract=abstract,
                date=datetime.now()  # SSRN doesn't always show dates clearly
            )
            papers.append(calculate_relevance(paper))
            
    except Exception as e:
        print(f"  Warning: Error scraping SSRN: {e}")
    
    return papers

# =============================================================================
# MAIN AGGREGATION
# =============================================================================

def fetch_all_papers(days: int = 7) -> list[Paper]:
    """Fetch papers from all sources."""
    cutoff_date = datetime.now() - timedelta(days=days)
    all_papers = []
    
    print(f"Fetching papers from last {days} days...\n")
    
    for source_name, config in SOURCES.items():
        print(f"  Fetching: {source_name}...")
        
        if config["type"] == "rss":
            papers = parse_rss_feed(source_name, config["url"], cutoff_date)
        elif config["type"] == "scrape_ssrn":
            papers = scrape_ssrn(source_name, config["url"], cutoff_date)
        else:
            papers = []
        
        all_papers.extend(papers)
        print(f"    Found {len(papers)} items")
        time.sleep(0.5)  # Be polite to servers
    
    return all_papers

def filter_and_rank(papers: list[Paper], min_score: int = 1) -> list[Paper]:
    """Filter to relevant papers and rank by score."""
    relevant = [p for p in papers if p.relevance_score >= min_score]
    return sorted(relevant, key=lambda x: x.relevance_score, reverse=True)

# =============================================================================
# OUTPUT GENERATION
# =============================================================================

def generate_markdown(papers: list[Paper], days: int) -> str:
    """Generate formatted markdown digest."""
    
    date_str = datetime.now().strftime("%B %d, %Y")
    
    output = f"""# Economics Research Digest
**Week of {date_str}** | Papers from last {days} days

---

## Top Papers by Relevance

"""
    
    if not papers:
        output += "*No highly relevant papers found this period. Consider expanding keywords or timeframe.*\n"
        return output
    
    # Group by relevance tier
    high_relevance = [p for p in papers if p.relevance_score >= 5]
    medium_relevance = [p for p in papers if 2 <= p.relevance_score < 5]
    other_relevant = [p for p in papers if 1 <= p.relevance_score < 2]
    
    if high_relevance:
        output += "### 🔴 High Priority\n\n"
        for p in high_relevance[:10]:
            output += format_paper(p)
    
    if medium_relevance:
        output += "\n### 🟡 Worth Reading\n\n"
        for p in medium_relevance[:10]:
            output += format_paper(p)
    
    if other_relevant:
        output += "\n### 🟢 Also Relevant\n\n"
        for p in other_relevant[:10]:
            output += format_paper(p)
    
    # Summary stats
    output += f"""
---

## Summary

- **Total papers scanned:** {len(papers) + len([p for p in papers if p.relevance_score == 0])}
- **Relevant papers found:** {len(papers)}
- **High priority:** {len(high_relevance)}
- **Sources checked:** {len(SOURCES)}

### Keywords Matched This Week
"""
    
    # Aggregate keyword matches
    all_keywords = []
    for p in papers:
        all_keywords.extend(p.matched_keywords)
    
    keyword_counts = {}
    for kw in all_keywords:
        keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    
    top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    for kw, count in top_keywords:
        output += f"- {kw}: {count} papers\n"
    
    return output

def format_paper(paper: Paper) -> str:
    """Format a single paper for markdown output."""
    date_str = paper.date.strftime("%b %d") if paper.date else "Recent"
    keywords = ", ".join(paper.matched_keywords[:5]) if paper.matched_keywords else ""
    
    output = f"""**[{paper.title}]({paper.url})**
*{paper.source}* | {paper.authors[:60]}{'...' if len(paper.authors) > 60 else ''} | {date_str}
"""
    
    if paper.key_finding:
        output += f"**📌 Key finding:** {paper.key_finding}\n"
    
    if paper.abstract and not paper.key_finding:
        # Only show abstract if we don't have a key finding
        abstract = paper.abstract[:300]
        if len(paper.abstract) > 300:
            abstract = abstract.rsplit(' ', 1)[0] + "..."
        output += f"> {abstract}\n"
    
    if keywords:
        output += f"**Keywords:** {keywords}\n"
    
    output += "\n"
    return output

# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate economics research digest")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--min-score", type=int, default=1, help="Minimum relevance score (default: 1)")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--summarize", type=int, default=15, help="Number of top papers to summarize (default: 15)")
    args = parser.parse_args()
    
    # Fetch and process
    all_papers = fetch_all_papers(days=args.days)
    relevant_papers = filter_and_rank(all_papers, min_score=args.min_score)
    
    print(f"\nFound {len(relevant_papers)} relevant papers out of {len(all_papers)} total")
    
    # Summarize top papers if API key is available
    if os.environ.get('ANTHROPIC_API_KEY') and args.summarize > 0:
        print(f"\nGenerating summaries for top {min(args.summarize, len(relevant_papers))} papers...")
        for i, paper in enumerate(relevant_papers[:args.summarize]):
            relevant_papers[i] = enrich_paper_with_summary(paper)
    else:
        print("\nNo ANTHROPIC_API_KEY found, skipping summaries")
    
    # Generate output
    markdown = generate_markdown(relevant_papers, args.days)
    
    # Save or print
    if args.output:
        output_path = args.output
    else:
        date_str = datetime.now().strftime("%Y%m%d")
        output_path = f"econ_digest_{date_str}.md"
    
    with open(output_path, "w") as f:
        f.write(markdown)
    
    print(f"\nDigest saved to: {output_path}")
    
    # Print preview
    print("\n" + "="*60)
    print("PREVIEW (first 2000 chars):")
    print("="*60 + "\n")
    print(markdown[:2000])
    if len(markdown) > 2000:
        print("\n... [truncated] ...")

if __name__ == "__main__":
    main()
