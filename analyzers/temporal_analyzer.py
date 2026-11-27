#!/usr/bin/env python3
"""
Temporal Analysis Module for Reddit Data
Analyzes temporal patterns, activity trends, and time-based insights.
"""

import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

class TemporalAnalyzer:
    """
    Analyzes temporal patterns in Reddit data including:
    - Activity trends over time
    - User cohort analysis
    - Peak activity periods
    - Seasonal patterns
    """

    def __init__(self, db_path: str, output_dir: str = "output/temporal_analysis"):
        """
        Initialize temporal analyzer.

        Args:
            db_path: Path to SQLite database
            output_dir: Directory for output files
        """
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Extract subreddit name from database path
        self.subreddit = Path(db_path).stem.replace('_historical_data', '')

    def generate_comprehensive_report(self,
                                    start_date: Optional[str] = None,
                                    end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate comprehensive temporal analysis report.

        Args:
            start_date: Start date for analysis (YYYY-MM-DD)
            end_date: End date for analysis (YYYY-MM-DD)

        Returns:
            Dictionary containing analysis results and file paths
        """
        results = {
            'subreddit': self.subreddit,
            'analysis_timestamp': datetime.now().isoformat(),
            'date_range': {'start': start_date, 'end': end_date},
            'files': {},
            'insights': {}
        }

        # Generate various temporal analyses
        results['files']['monthly_trends'] = self._analyze_monthly_trends(start_date, end_date)
        results['files']['daily_patterns'] = self._analyze_daily_patterns(start_date, end_date)
        results['files']['user_cohorts'] = self._analyze_user_cohorts(start_date, end_date)
        results['files']['peak_periods'] = self._identify_peak_periods(start_date, end_date)
        results['files']['activity_heatmap'] = self._create_activity_heatmap(start_date, end_date)

        # Generate insights
        results['insights'] = self._generate_insights(start_date, end_date)

        # Create HTML report
        results['files']['html_report'] = self._create_html_report(results)

        return results

    def _analyze_monthly_trends(self, start_date: Optional[str] = None,
                               end_date: Optional[str] = None) -> str:
        """Analyze monthly activity trends."""
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT
                strftime('%Y-%m', datetime(created_utc, 'unixepoch')) as month,
                COUNT(*) as total_posts,
                COUNT(DISTINCT author) as unique_authors,
                AVG(CAST(score AS REAL)) as avg_score,
                SUM(CAST(num_comments AS INTEGER)) as total_comments
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            query += " GROUP BY month ORDER BY month"

            df = pd.read_sql_query(query, conn)

        if df.empty:
            return None

        # Create visualization
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Monthly Posts', 'Unique Authors', 'Average Score', 'Total Comments'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )

        # Posts trend
        fig.add_trace(
            go.Scatter(x=df['month'], y=df['total_posts'], name='Posts', line=dict(color='blue')),
            row=1, col=1
        )

        # Unique authors
        fig.add_trace(
            go.Scatter(x=df['month'], y=df['unique_authors'], name='Authors', line=dict(color='green')),
            row=1, col=2
        )

        # Average score
        fig.add_trace(
            go.Scatter(x=df['month'], y=df['avg_score'], name='Avg Score', line=dict(color='red')),
            row=2, col=1
        )

        # Total comments
        fig.add_trace(
            go.Scatter(x=df['month'], y=df['total_comments'], name='Comments', line=dict(color='purple')),
            row=2, col=2
        )

        fig.update_layout(
            title=f"Monthly Trends - r/{self.subreddit}",
            height=600,
            showlegend=False
        )

        output_path = self.output_dir / f"{self.subreddit}_monthly_trends.html"
        fig.write_html(str(output_path), include_plotlyjs='directory')

        return str(output_path)

    def _analyze_daily_patterns(self, start_date: Optional[str] = None,
                               end_date: Optional[str] = None) -> str:
        """Analyze daily activity patterns."""
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT
                strftime('%w', datetime(created_utc, 'unixepoch')) as day_of_week,
                strftime('%H', datetime(created_utc, 'unixepoch')) as hour,
                COUNT(*) as post_count
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            query += " GROUP BY day_of_week, hour ORDER BY day_of_week, hour"

            df = pd.read_sql_query(query, conn)

        if df.empty:
            return None

        # Create heatmap data
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        hours = list(range(24))

        heatmap_data = []
        for day_num in range(7):
            day_data = []
            for hour in range(24):
                count = df[(df['day_of_week'] == str(day_num)) & (df['hour'] == f"{hour:02d}")]['post_count'].sum()
                day_data.append(count)
            heatmap_data.append(day_data)

        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data,
            x=[f"{h}:00" for h in hours],
            y=days,
            colorscale='Viridis'
        ))

        fig.update_layout(
            title=f"Daily Activity Patterns - r/{self.subreddit}",
            xaxis_title="Hour of Day",
            yaxis_title="Day of Week",
            height=400
        )

        output_path = self.output_dir / f"{self.subreddit}_daily_patterns.html"
        fig.write_html(str(output_path), include_plotlyjs='directory')

        return str(output_path)

    def _analyze_user_cohorts(self, start_date: Optional[str] = None,
                             end_date: Optional[str] = None) -> str:
        """Analyze user cohorts and retention patterns."""
        with sqlite3.connect(self.db_path) as conn:
            # Get user first activity dates
            query = """
            SELECT
                author,
                MIN(datetime(created_utc, 'unixepoch')) as first_activity,
                COUNT(*) as total_posts,
                strftime('%Y-%m', MIN(datetime(created_utc, 'unixepoch'))) as cohort_month
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            query += " GROUP BY author ORDER BY first_activity"

            df = pd.read_sql_query(query, conn)

        if df.empty:
            return None

        # Analyze cohort sizes and activity
        cohort_analysis = df.groupby('cohort_month').agg({
            'author': 'count',
            'total_posts': ['mean', 'median', 'sum']
        }).round(2)

        cohort_analysis.columns = ['Users', 'Avg Posts/User', 'Median Posts/User', 'Total Posts']

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('New Users per Month', 'Posts per User by Cohort')
        )

        # New users per month
        fig.add_trace(
            go.Bar(x=cohort_analysis.index, y=cohort_analysis['Users'], name='New Users'),
            row=1, col=1
        )

        # Average posts per user
        fig.add_trace(
            go.Scatter(x=cohort_analysis.index, y=cohort_analysis['Avg Posts/User'],
                      name='Avg Posts/User', mode='lines+markers'),
            row=2, col=1
        )

        fig.update_layout(
            title=f"User Cohort Analysis - r/{self.subreddit}",
            height=600,
            showlegend=True
        )

        output_path = self.output_dir / f"{self.subreddit}_user_cohorts.html"
        fig.write_html(str(output_path), include_plotlyjs='directory')

        return str(output_path)

    def _identify_peak_periods(self, start_date: Optional[str] = None,
                              end_date: Optional[str] = None) -> str:
        """Identify and analyze peak activity periods."""
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT
                date(datetime(created_utc, 'unixepoch')) as date,
                COUNT(*) as daily_posts,
                COUNT(DISTINCT author) as daily_authors,
                AVG(CAST(score AS REAL)) as avg_score
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            query += " GROUP BY date ORDER BY date"

            df = pd.read_sql_query(query, conn)

        if df.empty:
            return None

        # Identify peaks using statistical methods
        mean_posts = df['daily_posts'].mean()
        std_posts = df['daily_posts'].std()
        threshold = mean_posts + 2 * std_posts  # 2 standard deviations above mean

        peak_days = df[df['daily_posts'] > threshold].copy()

        fig = go.Figure()

        # Daily activity
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['daily_posts'],
            mode='lines',
            name='Daily Posts',
            line=dict(color='blue')
        ))

        # Peak threshold line
        fig.add_hline(
            y=threshold,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Peak Threshold ({threshold:.1f})"
        )

        # Mark peak days
        if not peak_days.empty:
            fig.add_trace(go.Scatter(
                x=peak_days['date'],
                y=peak_days['daily_posts'],
                mode='markers',
                name='Peak Days',
                marker=dict(color='red', size=8)
            ))

        fig.update_layout(
            title=f"Peak Activity Periods - r/{self.subreddit}",
            xaxis_title="Date",
            yaxis_title="Daily Posts",
            height=400
        )

        output_path = self.output_dir / f"{self.subreddit}_peak_periods.html"
        fig.write_html(str(output_path), include_plotlyjs='directory')

        return str(output_path)

    def _create_activity_heatmap(self, start_date: Optional[str] = None,
                                end_date: Optional[str] = None) -> str:
        """Create calendar heatmap of daily activity."""
        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT
                date(datetime(created_utc, 'unixepoch')) as date,
                COUNT(*) as posts
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            query += " GROUP BY date ORDER BY date"

            df = pd.read_sql_query(query, conn)

        if df.empty:
            return None

        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.month
        df['day'] = df['date'].dt.day

        fig = px.density_heatmap(
            df,
            x='month',
            y='day',
            z='posts',
            facet_col='year',
            title=f"Activity Calendar Heatmap - r/{self.subreddit}",
            labels={'month': 'Month', 'day': 'Day', 'posts': 'Posts'}
        )

        output_path = self.output_dir / f"{self.subreddit}_activity_heatmap.html"
        fig.write_html(str(output_path), include_plotlyjs='directory')

        return str(output_path)

    def _generate_insights(self, start_date: Optional[str] = None,
                          end_date: Optional[str] = None) -> Dict[str, Any]:
        """Generate key insights from temporal analysis."""
        insights = {}

        with sqlite3.connect(self.db_path) as conn:
            # Overall activity summary
            query = """
            SELECT
                COUNT(*) as total_posts,
                COUNT(DISTINCT author) as unique_authors,
                MIN(datetime(created_utc, 'unixepoch')) as earliest_post,
                MAX(datetime(created_utc, 'unixepoch')) as latest_post,
                AVG(CAST(score AS REAL)) as avg_score
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            summary = pd.read_sql_query(query, conn).iloc[0].to_dict()
            insights['summary'] = summary

            # Peak activity day
            peak_query = """
            SELECT
                date(datetime(created_utc, 'unixepoch')) as date,
                COUNT(*) as posts
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                peak_query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                peak_query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            peak_query += " GROUP BY date ORDER BY posts DESC LIMIT 1"

            peak_day = pd.read_sql_query(peak_query, conn)
            if not peak_day.empty:
                insights['peak_day'] = peak_day.iloc[0].to_dict()

            # Most active hour
            hour_query = """
            SELECT
                strftime('%H', datetime(created_utc, 'unixepoch')) as hour,
                COUNT(*) as posts
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            """

            if start_date:
                hour_query += f" AND date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                hour_query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            hour_query += " GROUP BY hour ORDER BY posts DESC LIMIT 1"

            peak_hour = pd.read_sql_query(hour_query, conn)
            if not peak_hour.empty:
                insights['peak_hour'] = peak_hour.iloc[0].to_dict()

        return insights

    @staticmethod
    def _fmt(value: Any, spec: str) -> str:
        """Format a number, or return N/A when a date range matched no posts."""
        return format(value, spec) if isinstance(value, (int, float)) else 'N/A'

    def _create_html_report(self, results: Dict[str, Any]) -> str:
        """Create comprehensive HTML report."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Temporal Analysis Report - r/{self.subreddit}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
                .insight {{ background-color: #e9ecef; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                .file-link {{ display: block; margin: 5px 0; padding: 10px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px; }}
                .file-link:hover {{ background-color: #0056b3; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Temporal Analysis Report: r/{self.subreddit}</h1>
                <p>Generated on: {results['analysis_timestamp']}</p>
                {f"<p>Date Range: {results['date_range']['start']} to {results['date_range']['end']}</p>" if results['date_range']['start'] else ""}
            </div>

            <h2>Key Insights</h2>
        """

        if 'summary' in results['insights']:
            summary = results['insights']['summary']
            html_content += f"""
            <div class="insight">
                <h3>Overall Activity</h3>
                <ul>
                    <li>Total Posts: {self._fmt(summary.get('total_posts'), ',')}</li>
                    <li>Unique Authors: {self._fmt(summary.get('unique_authors'), ',')}</li>
                    <li>Average Score: {self._fmt(summary.get('avg_score'), '.2f')}</li>
                    <li>Time Span: {summary.get('earliest_post', 'N/A')} to {summary.get('latest_post', 'N/A')}</li>
                </ul>
            </div>
            """

        if 'peak_day' in results['insights']:
            peak_day = results['insights']['peak_day']
            html_content += f"""
            <div class="insight">
                <h3>Peak Activity</h3>
                <ul>
                    <li>Peak Day: {peak_day.get('date', 'N/A')} ({peak_day.get('posts', 'N/A')} posts)</li>
                    {f"<li>Peak Hour: {results['insights']['peak_hour']['hour']}:00 ({results['insights']['peak_hour']['posts']} posts)</li>" if 'peak_hour' in results['insights'] else ""}
                </ul>
            </div>
            """

        html_content += "<h2>Detailed Analysis</h2>"

        for analysis_type, file_path in results['files'].items():
            if file_path and file_path != str(self.output_dir / f"{self.subreddit}_temporal_report.html"):
                html_content += f'<a href="{Path(file_path).name}" class="file-link">{analysis_type.replace("_", " ").title()}</a>'

        html_content += """
            </body>
        </html>
        """

        output_path = self.output_dir / f"{self.subreddit}_temporal_report.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(output_path)

    def export_data(self, format: str = 'json') -> str:
        """Export temporal analysis data."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        with sqlite3.connect(self.db_path) as conn:
            query = """
            SELECT
                datetime(created_utc, 'unixepoch') as timestamp,
                strftime('%Y-%m', datetime(created_utc, 'unixepoch')) as month,
                strftime('%Y-%m-%d', datetime(created_utc, 'unixepoch')) as date,
                strftime('%H', datetime(created_utc, 'unixepoch')) as hour,
                strftime('%w', datetime(created_utc, 'unixepoch')) as day_of_week,
                author,
                score,
                num_comments,
                title
            FROM submissions
            WHERE author != '[deleted]' AND created_utc IS NOT NULL
            ORDER BY created_utc
            """

            df = pd.read_sql_query(query, conn)

        if format == 'json':
            output_path = self.output_dir / f"{self.subreddit}_temporal_data_{timestamp}.json"
            df.to_json(output_path, orient='records', date_format='iso')
        elif format == 'csv':
            output_path = self.output_dir / f"{self.subreddit}_temporal_data_{timestamp}.csv"
            df.to_csv(output_path, index=False)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return str(output_path)