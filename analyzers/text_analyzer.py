#!/usr/bin/env python3
"""
Text Analysis Module for Reddit Data
Comprehensive text analysis including NLP, sentiment, and topic modeling.
"""

import sqlite3
import pandas as pd
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter, defaultdict
import logging

# NLP libraries
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.stem import PorterStemmer, WordNetLemmatizer
    from nltk.sentiment import SentimentIntensityAnalyzer
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    logging.warning("NLTK not available. Some text analysis features will be limited.")

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not available. Topic modeling and clustering will be disabled.")

class TextAnalyzer:
    """
    Comprehensive text analysis for Reddit data including:
    - Word frequency analysis
    - Sentiment analysis
    - Topic modeling
    - Keyword extraction
    - Text clustering
    """

    def __init__(self, db_path: str, output_dir: str = "output/text_analysis"):
        """
        Initialize text analyzer.

        Args:
            db_path: Path to SQLite database
            output_dir: Directory for output files
        """
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Extract subreddit name from database path
        self.subreddit = Path(db_path).stem.replace('_historical_data', '')

        # Initialize NLP components if available
        self._setup_nlp()

        # Text preprocessing settings
        self.min_word_length = 3
        self.max_word_length = 20
        self.stop_words = self._get_stop_words()

    def _setup_nlp(self):
        """Set up NLTK components, downloading their data files when needed.

        Each feature is switched on only if it works on this machine. A
        computer that cannot download NLTK's data (offline, or behind a
        firewall) still gets the basic analysis.
        """
        self.has_tokenizer = False
        self.has_stopwords = False
        self.has_lemmatizer = False
        self.has_vader = False
        if not NLTK_AVAILABLE:
            return

        def works(probe) -> bool:
            try:
                probe()
                return True
            except Exception:
                return False

        def ensure(probe, *packages) -> bool:
            if works(probe):
                return True
            for package in packages:
                try:
                    nltk.download(package, quiet=True)
                except Exception:
                    pass
            return works(probe)

        self.has_tokenizer = ensure(lambda: word_tokenize("A short test."), 'punkt', 'punkt_tab')
        self.has_stopwords = ensure(lambda: stopwords.words('english'), 'stopwords')
        self.has_lemmatizer = ensure(lambda: WordNetLemmatizer().lemmatize('tests'), 'wordnet', 'omw-1.4')
        self.has_vader = ensure(lambda: SentimentIntensityAnalyzer(), 'vader_lexicon')

        self.stemmer = PorterStemmer()
        if self.has_lemmatizer:
            self.lemmatizer = WordNetLemmatizer()
        if self.has_vader:
            self.sentiment_analyzer = SentimentIntensityAnalyzer()

        missing = [name for name, ready in (
            ('tokenizer', self.has_tokenizer), ('stop words', self.has_stopwords),
            ('lemmatizer', self.has_lemmatizer), ('sentiment lexicon', self.has_vader)) if not ready]
        if missing:
            logging.warning(
                "NLTK data could not be loaded for: %s. Those features fall back to basic mode. "
                "To fetch the data, run: python -m nltk.downloader punkt punkt_tab stopwords wordnet vader_lexicon",
                ', '.join(missing))

    def _get_stop_words(self) -> set:
        """Get comprehensive stop words list."""
        # A compact English list, so word counts are meaningful even when
        # NLTK or its data files are absent.
        stop_words = set("""
            a about above after again against all am an and any are as at be because been before
            being below between both but by can did do does doing down during each few for from
            further had has have having he her here hers herself him himself his how i if in into
            is it its itself me more most my myself no nor not of off on once only or other our
            ours ourselves out over own same she so some such than that the their theirs them
            themselves then there these they this those through to too under until up very was we
            were what when where which while who whom why will with you your yours yourself
            yourselves im ive id dont doesnt didnt isnt arent wasnt werent cant wont wouldnt
            couldnt shouldnt thats theres theyre youre hes shes its lets got one two much many
            even still well back going been
        """.split())

        if self.has_stopwords:
            stop_words.update(stopwords.words('english'))

        # Add common Reddit/internet stop words
        reddit_stops = {
            'like', 'just', 'get', 'go', 'know', 'think', 'see', 'would', 'could',
            'should', 'really', 'also', 'make', 'take', 'come', 'way', 'time',
            'people', 'good', 'want', 'need', 'edit', 'delete', 'removed',
            'reddit', 'post', 'comment', 'upvote', 'downvote', 'karma'
        }
        stop_words.update(reddit_stops)

        return stop_words

    def analyze_text_comprehensively(self,
                                   content_types: List[str] = ['submissions', 'comments'],
                                   start_date: Optional[str] = None,
                                   end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform comprehensive text analysis.

        Args:
            content_types: Types of content to analyze ('submissions', 'comments')
            start_date: Start date for analysis (YYYY-MM-DD)
            end_date: End date for analysis (YYYY-MM-DD)

        Returns:
            Dictionary containing analysis results and file paths
        """
        results = {
            'subreddit': self.subreddit,
            'analysis_timestamp': datetime.now().isoformat(),
            'content_types': content_types,
            'date_range': {'start': start_date, 'end': end_date},
            'files': {},
            'statistics': {}
        }

        # Load text data
        text_data = self._load_text_data(content_types, start_date, end_date)

        if not text_data:
            logging.warning("No text data found for analysis")
            return results

        # Perform various analyses
        results['files']['word_frequency'] = self._analyze_word_frequency(text_data)
        results['files']['phrase_analysis'] = self._analyze_phrases(text_data)

        if self.has_vader or TEXTBLOB_AVAILABLE:
            results['files']['sentiment_analysis'] = self._analyze_sentiment(text_data)

        if SKLEARN_AVAILABLE:
            results['files']['topic_modeling'] = self._perform_topic_modeling(text_data)
            results['files']['keyword_extraction'] = self._extract_keywords(text_data)

        # Generate statistics
        results['statistics'] = self._generate_text_statistics(text_data)

        # Create comprehensive HTML report
        results['files']['html_report'] = self._create_text_report(results, text_data)

        return results

    def _load_text_data(self,
                       content_types: List[str],
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load text data from database."""
        text_data = []

        with sqlite3.connect(self.db_path) as conn:
            for content_type in content_types:
                if content_type == 'submissions':
                    query = """
                    SELECT id, title, selftext, author, created_utc, score, 'submission' as type
                    FROM submissions
                    WHERE author != '[deleted]' AND (title IS NOT NULL OR selftext IS NOT NULL)
                    """
                elif content_type == 'comments':
                    query = """
                    SELECT id, body as text, author, created_utc, score, 'comment' as type
                    FROM comments
                    WHERE author != '[deleted]' AND body IS NOT NULL AND body != '[deleted]'
                    """
                else:
                    continue

                if start_date:
                    query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
                if end_date:
                    query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

                query += " ORDER BY created_utc"

                df = pd.read_sql_query(query, conn)

                for _, row in df.iterrows():
                    item = row.to_dict()

                    # Combine title and selftext for submissions
                    if content_type == 'submissions':
                        text_parts = []
                        if pd.notna(row['title']):
                            text_parts.append(str(row['title']))
                        if pd.notna(row['selftext']) and str(row['selftext']).strip():
                            text_parts.append(str(row['selftext']))
                        item['text'] = ' '.join(text_parts)
                    else:
                        item['text'] = str(row['text']) if pd.notna(row['text']) else ''

                    if item['text'].strip():
                        text_data.append(item)

        return text_data

    def _preprocess_text(self, text: str) -> List[str]:
        """Preprocess text for analysis."""
        if not text:
            return []

        # Convert to lowercase
        text = text.lower()

        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)

        # Remove Reddit formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)   # Bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)       # Italic
        text = re.sub(r'~~(.*?)~~', r'\1', text)       # Strikethrough
        text = re.sub(r'\^(.*?)\^', r'\1', text)       # Superscript
        text = re.sub(r'&gt;.*?(\n|$)', ' ', text)      # Quotes
        text = re.sub(r'/u/[A-Za-z0-9_-]+', '', text) # User mentions
        text = re.sub(r'/r/[A-Za-z0-9_-]+', '', text) # Subreddit mentions

        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^a-zA-Z0-9\s.,!?;:-]', ' ', text)

        # Tokenize
        if self.has_tokenizer:
            words = word_tokenize(text)
        else:
            # Without NLTK's tokenizer, take runs of letters so that trailing
            # punctuation does not cost a word ("credits," -> "credits").
            words = re.findall(r"[A-Za-z]+", text)

        # Filter words
        filtered_words = []
        for word in words:
            if (self.min_word_length <= len(word) <= self.max_word_length and
                word.lower() not in self.stop_words and
                not word.isdigit() and
                word.isalpha()):

                # Lemmatize if available
                if self.has_lemmatizer:
                    word = self.lemmatizer.lemmatize(word.lower())

                filtered_words.append(word.lower())

        return filtered_words

    def _analyze_word_frequency(self, text_data: List[Dict[str, Any]]) -> str:
        """Analyze word frequency patterns."""
        all_words = []
        word_by_time = defaultdict(Counter)
        word_by_author = defaultdict(Counter)

        for item in text_data:
            words = self._preprocess_text(item['text'])
            all_words.extend(words)

            # Time-based analysis
            if item.get('created_utc'):
                from datetime import datetime
                month = datetime.fromtimestamp(item['created_utc']).strftime('%Y-%m')
                word_by_time[month].update(words)

            # Author-based analysis
            if item.get('author'):
                word_by_author[item['author']].update(words)

        # Overall frequency
        word_freq = Counter(all_words)
        top_words = word_freq.most_common(50)

        # Create visualization data
        analysis_results = {
            'total_words': len(all_words),
            'unique_words': len(word_freq),
            'top_words': top_words,
            'vocabulary_richness': len(word_freq) / len(all_words) if all_words else 0,
            'temporal_trends': {month: dict(counter.most_common(10)) for month, counter in word_by_time.items()},
            'prolific_authors': {author: sum(counter.values()) for author, counter in word_by_author.items()}
        }

        # Export results
        output_path = self.output_dir / f"{self.subreddit}_word_frequency.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_results, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _analyze_phrases(self, text_data: List[Dict[str, Any]]) -> str:
        """Analyze common phrases and n-grams."""
        from itertools import combinations

        all_text = ' '.join([item['text'] for item in text_data])

        # Bigrams and trigrams
        bigrams = Counter()
        trigrams = Counter()

        for item in text_data:
            words = self._preprocess_text(item['text'])

            # Generate bigrams
            for i in range(len(words) - 1):
                bigram = f"{words[i]} {words[i+1]}"
                bigrams[bigram] += 1

            # Generate trigrams
            for i in range(len(words) - 2):
                trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
                trigrams[trigram] += 1

        phrase_analysis = {
            'top_bigrams': bigrams.most_common(30),
            'top_trigrams': trigrams.most_common(20),
            'phrase_statistics': {
                'total_bigrams': sum(bigrams.values()),
                'unique_bigrams': len(bigrams),
                'total_trigrams': sum(trigrams.values()),
                'unique_trigrams': len(trigrams)
            }
        }

        output_path = self.output_dir / f"{self.subreddit}_phrase_analysis.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(phrase_analysis, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _analyze_sentiment(self, text_data: List[Dict[str, Any]]) -> str:
        """Analyze sentiment patterns in text data."""
        sentiment_results = []

        for item in text_data:
            text = item['text']
            sentiment = {'id': item['id'], 'type': item['type']}

            if self.has_vader:
                # VADER sentiment analysis
                vader_scores = self.sentiment_analyzer.polarity_scores(text)
                sentiment.update({
                    'vader_compound': vader_scores['compound'],
                    'vader_positive': vader_scores['pos'],
                    'vader_negative': vader_scores['neg'],
                    'vader_neutral': vader_scores['neu']
                })

            if TEXTBLOB_AVAILABLE:
                # TextBlob sentiment analysis
                blob = TextBlob(text)
                sentiment.update({
                    'textblob_polarity': blob.sentiment.polarity,
                    'textblob_subjectivity': blob.sentiment.subjectivity
                })

            # Add metadata
            sentiment.update({
                'author': item.get('author'),
                'created_utc': item.get('created_utc'),
                'score': item.get('score'),
                'text_length': len(text)
            })

            sentiment_results.append(sentiment)

        # Aggregate sentiment statistics
        if sentiment_results:
            sentiment_stats = self._calculate_sentiment_stats(sentiment_results)
        else:
            sentiment_stats = {}

        analysis_results = {
            'individual_sentiments': sentiment_results,
            'aggregate_statistics': sentiment_stats,
            'temporal_sentiment': self._analyze_temporal_sentiment(sentiment_results)
        }

        output_path = self.output_dir / f"{self.subreddit}_sentiment_analysis.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_results, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _calculate_sentiment_stats(self, sentiment_results: List[Dict]) -> Dict[str, Any]:
        """Calculate aggregate sentiment statistics."""
        stats = {}

        if self.has_vader:
            vader_compounds = [s['vader_compound'] for s in sentiment_results if 'vader_compound' in s]
            if vader_compounds:
                stats['vader'] = {
                    'mean_compound': sum(vader_compounds) / len(vader_compounds),
                    'positive_ratio': len([s for s in vader_compounds if s > 0.05]) / len(vader_compounds),
                    'negative_ratio': len([s for s in vader_compounds if s < -0.05]) / len(vader_compounds),
                    'neutral_ratio': len([s for s in vader_compounds if -0.05 <= s <= 0.05]) / len(vader_compounds)
                }

        if TEXTBLOB_AVAILABLE:
            textblob_polarities = [s['textblob_polarity'] for s in sentiment_results if 'textblob_polarity' in s]
            if textblob_polarities:
                stats['textblob'] = {
                    'mean_polarity': sum(textblob_polarities) / len(textblob_polarities),
                    'positive_ratio': len([s for s in textblob_polarities if s > 0.1]) / len(textblob_polarities),
                    'negative_ratio': len([s for s in textblob_polarities if s < -0.1]) / len(textblob_polarities)
                }

        return stats

    def _analyze_temporal_sentiment(self, sentiment_results: List[Dict]) -> Dict[str, Any]:
        """Analyze sentiment trends over time."""
        from datetime import datetime

        temporal_sentiment = defaultdict(list)

        for item in sentiment_results:
            if item.get('created_utc') and 'vader_compound' in item:
                month = datetime.fromtimestamp(item['created_utc']).strftime('%Y-%m')
                temporal_sentiment[month].append(item['vader_compound'])

        # Calculate monthly averages
        monthly_sentiment = {}
        for month, scores in temporal_sentiment.items():
            monthly_sentiment[month] = {
                'mean_sentiment': sum(scores) / len(scores),
                'count': len(scores)
            }

        return monthly_sentiment

    def _perform_topic_modeling(self, text_data: List[Dict[str, Any]], n_topics: int = 10) -> str:
        """Perform topic modeling using LDA."""
        if not SKLEARN_AVAILABLE:
            return None

        # Prepare documents
        documents = []
        for item in text_data:
            processed_words = self._preprocess_text(item['text'])
            if len(processed_words) > 5:  # Only include substantial texts
                documents.append(' '.join(processed_words))

        if len(documents) < n_topics:
            n_topics = max(2, len(documents) // 2)

        # TF-IDF Vectorization
        vectorizer = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.8
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(documents)
        except ValueError as exc:
            # Too few documents, or too little shared vocabulary, to model topics.
            logging.warning(f"Topic modeling skipped: {exc}")
            return None
        feature_names = vectorizer.get_feature_names_out()

        # LDA Topic Modeling
        lda = LatentDirichletAllocation(
            n_components=n_topics,
            max_iter=10,
            random_state=42
        )

        lda.fit(tfidf_matrix)

        # Extract topics
        topics = []
        for topic_idx, topic in enumerate(lda.components_):
            top_words_idx = topic.argsort()[-10:][::-1]
            top_words = [feature_names[i] for i in top_words_idx]
            topics.append({
                'topic_id': topic_idx,
                'top_words': top_words,
                'word_weights': [topic[i] for i in top_words_idx]
            })

        # Document-topic assignments
        doc_topics = lda.transform(tfidf_matrix)
        document_topics = []
        for i, doc_topic_dist in enumerate(doc_topics):
            document_topics.append({
                'document_index': i,
                'primary_topic': int(doc_topic_dist.argmax()),
                'topic_probabilities': doc_topic_dist.tolist()
            })

        results = {
            'n_topics': n_topics,
            'topics': topics,
            'document_topics': document_topics[:100],  # Limit for file size
            'model_perplexity': lda.perplexity(tfidf_matrix),
            'total_documents': len(documents)
        }

        output_path = self.output_dir / f"{self.subreddit}_topic_modeling.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _extract_keywords(self, text_data: List[Dict[str, Any]]) -> str:
        """Extract keywords using TF-IDF."""
        if not SKLEARN_AVAILABLE:
            return None

        # Prepare documents
        documents = []
        for item in text_data:
            processed_words = self._preprocess_text(item['text'])
            if processed_words:
                documents.append(' '.join(processed_words))

        # TF-IDF for keyword extraction
        vectorizer = TfidfVectorizer(
            max_features=200,
            ngram_range=(1, 3),
            min_df=2,
            max_df=0.7
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(documents)
        except ValueError as exc:
            logging.warning(f"Keyword extraction skipped: {exc}")
            return None
        feature_names = vectorizer.get_feature_names_out()

        # Calculate average TF-IDF scores
        mean_scores = tfidf_matrix.mean(axis=0).A1
        keyword_scores = list(zip(feature_names, mean_scores))
        keyword_scores.sort(key=lambda x: x[1], reverse=True)

        results = {
            'top_keywords': keyword_scores[:50],
            'extraction_method': 'TF-IDF',
            'total_documents': len(documents),
            'vocabulary_size': len(feature_names)
        }

        output_path = self.output_dir / f"{self.subreddit}_keyword_extraction.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _generate_text_statistics(self, text_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive text statistics."""
        stats = {
            'total_items': len(text_data),
            'content_type_distribution': Counter([item['type'] for item in text_data]),
            'text_length_stats': {},
            'author_stats': {},
            'temporal_stats': {}
        }

        # Text length statistics
        text_lengths = [len(item['text']) for item in text_data]
        word_counts = [len(self._preprocess_text(item['text'])) for item in text_data]

        stats['text_length_stats'] = {
            'mean_characters': sum(text_lengths) / len(text_lengths) if text_lengths else 0,
            'mean_words': sum(word_counts) / len(word_counts) if word_counts else 0,
            'max_characters': max(text_lengths) if text_lengths else 0,
            'max_words': max(word_counts) if word_counts else 0,
            'total_characters': sum(text_lengths),
            'total_words': sum(word_counts)
        }

        # Author statistics
        author_counts = Counter([item['author'] for item in text_data if item.get('author')])
        stats['author_stats'] = {
            'unique_authors': len(author_counts),
            'most_prolific': author_counts.most_common(10),
            'posts_per_author': sum(author_counts.values()) / len(author_counts) if author_counts else 0
        }

        # Temporal statistics
        if any(item.get('created_utc') for item in text_data):
            from datetime import datetime
            timestamps = [item['created_utc'] for item in text_data if item.get('created_utc')]
            dates = [datetime.fromtimestamp(ts).date() for ts in timestamps]

            stats['temporal_stats'] = {
                'date_range': {
                    'start': min(dates).isoformat() if dates else None,
                    'end': max(dates).isoformat() if dates else None
                },
                'total_days': (max(dates) - min(dates)).days + 1 if dates else 0,
                'posts_per_day': len(dates) / ((max(dates) - min(dates)).days + 1) if dates else 0
            }

        return stats

    def _create_text_report(self, results: Dict[str, Any], text_data: List[Dict[str, Any]]) -> str:
        """Create comprehensive HTML report for text analysis."""
        from datetime import datetime

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Text Analysis Report - r/{self.subreddit}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .stat {{ display: inline-block; margin: 10px 15px 10px 0; }}
                .file-link {{ display: block; margin: 5px 0; padding: 10px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px; }}
                .file-link:hover {{ background-color: #0056b3; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Text Analysis Report: r/{self.subreddit}</h1>
                <p>Generated on: {results['analysis_timestamp']}</p>
                <p>Content Types: {', '.join(results['content_types'])}</p>
                {f"<p>Date Range: {results['date_range']['start']} to {results['date_range']['end']}</p>" if results['date_range']['start'] else ""}
            </div>

            <div class="section">
                <h2>Overview Statistics</h2>
        """

        if 'statistics' in results:
            stats = results['statistics']
            html_content += f"""
                <div class="stat"><strong>Total Items:</strong> {stats['total_items']:,}</div>
                <div class="stat"><strong>Total Words:</strong> {stats['text_length_stats']['total_words']:,}</div>
                <div class="stat"><strong>Unique Authors:</strong> {stats['author_stats']['unique_authors']:,}</div>
                <div class="stat"><strong>Avg Words/Item:</strong> {stats['text_length_stats']['mean_words']:.1f}</div>
                <div class="stat"><strong>Vocabulary Richness:</strong> {stats.get('vocabulary_richness', 0):.3f}</div>
            """

            if stats['author_stats']['most_prolific']:
                html_content += """
                <h3>Most Active Authors</h3>
                <table>
                    <tr><th>Author</th><th>Posts</th></tr>
                """
                for author, count in stats['author_stats']['most_prolific'][:10]:
                    html_content += f"<tr><td>{author}</td><td>{count}</td></tr>"
                html_content += "</table>"

        html_content += "</div><div class='section'><h2>Analysis Files</h2>"

        for analysis_type, file_path in results['files'].items():
            if file_path and analysis_type != 'html_report':
                html_content += f'<a href="{Path(file_path).name}" class="file-link">{analysis_type.replace("_", " ").title()}</a>'

        html_content += """
            </div>
        </body>
        </html>
        """

        output_path = self.output_dir / f"{self.subreddit}_text_analysis_report.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(output_path)

    def export_corpus(self, format: str = 'jsonl', min_length: int = 10) -> str:
        """Export text corpus for external analysis."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        text_data = self._load_text_data(['submissions', 'comments'])
        filtered_data = [item for item in text_data if len(item['text']) >= min_length]

        if format == 'jsonl':
            output_path = self.output_dir / f"{self.subreddit}_corpus_{timestamp}.jsonl"
            with open(output_path, 'w', encoding='utf-8') as f:
                for item in filtered_data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

        elif format == 'txt':
            output_path = self.output_dir / f"{self.subreddit}_corpus_{timestamp}.txt"
            with open(output_path, 'w', encoding='utf-8') as f:
                for item in filtered_data:
                    f.write(item['text'] + '\n\n')

        else:
            raise ValueError(f"Unsupported format: {format}")

        return str(output_path)